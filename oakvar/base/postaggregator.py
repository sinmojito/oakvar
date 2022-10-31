class BasePostAggregator(object):

    cr_type_to_sql = {"string": "text", "int": "integer", "float": "real"}

    def __init__(self, cmd_args, status_writer):
        from ..util.util import get_caller_name

        self.status_writer = status_writer
        self.cmd_arg_parser = None
        self.run_name = None
        self.output_dir = None
        self.level = None
        self.levelno = None
        self.confs = None
        self.db_path = None
        self.logger = None
        self.error_logger = None
        self.unique_excs = None
        self.module_name = get_caller_name(cmd_args[0])
        self.parse_cmd_args(cmd_args)
        self._setup_logger()
        self.make_conf_and_level()
        self.fix_col_names()
        self.dbconn = None
        self.cursor = None
        self.cursor_w = None
        self._open_db_connection()
        self.should_run_annotate = self.check()

    def make_conf_and_level(self):
        from ..module.local import get_module_conf
        from ..exceptions import SetupError
        from ..consts import LEVELS

        self.conf = get_module_conf(self.module_name, module_type="postaggregator")
        if self.conf and self.conf.get("level"):
            self.level = self.conf.get("level")
        if not self.level:
            raise SetupError(msg="level is not defined in {self.module_name}")
        if self.level:
            self.levelno = LEVELS[self.level]

    def check(self):
        """
        Return boolean indicating whether main 'annotate' loop should be run.
        Should be overridden in sub-classes.
        """
        return True

    def fix_col_names(self):
        if self.conf is None:
            from ..exceptions import ConfigurationError

            raise ConfigurationError()
        for col in self.conf["output_columns"]:
            col["name"] = self.module_name + "__" + col["name"]

    def _log_exception(self, e, halt=True):
        if halt:
            raise e
        else:
            if self.logger:
                self.logger.exception(e)

    def _define_cmd_parser(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-n", dest="run_name", help="name of oakvar run")
        parser.add_argument(
            "-d",
            dest="output_dir",
            help="Output directory. " + "Default is input file directory.",
        )
        #parser.add_argument(
        #    "-l",
        #    dest="level",
        #    default="variant",
        #    help="Summarize level. " + "Default is variant.",
        #)
        parser.add_argument(
            "--confs", dest="confs", default="{}", help="Configuration string"
        )
        self.cmd_arg_parser = parser

    def parse_cmd_args(self, cmd_args):
        import os
        import json
        from ..exceptions import SetupError
        from ..exceptions import ParserError

        self._define_cmd_parser()
        if self.cmd_arg_parser is None:
            raise ParserError("postaggregator")
        parsed_args = self.cmd_arg_parser.parse_args(cmd_args[1:])
        if parsed_args.run_name:
            self.run_name = parsed_args.run_name
        if parsed_args.output_dir:
            self.output_dir = parsed_args.output_dir
        if self.output_dir is None:
            raise SetupError("Output directory was not given.")
        if self.run_name is None:
            raise ParserError("postaggregator run_name")
        self.db_path = os.path.join(self.output_dir, self.run_name + ".sqlite")
        self.confs = None
        if parsed_args.confs is not None:
            confs = parsed_args.confs.lstrip("'").rstrip("'").replace("'", '"')
            self.confs = json.loads(confs)

    def handle_legacy_data(self, output_dict: dict):
        from json import dumps

        for colname in self.json_colnames:
            delflag = False
            json_data = output_dict.get(colname, None)
            if json_data and "__" in colname:
                shortcolname = colname.split("__")[1]
                json_data = output_dict.get(shortcolname, None)
                delflag = json_data is not None
            if json_data:
                if type(json_data) is list:
                    for rowidx in range(len(json_data)):
                        row = json_data[rowidx]
                        if type(row) is list:
                            pass
                        elif type(row) is dict:
                            list_data = []
                            table_header = self.table_headers[colname]
                            for i in range(len(table_header)):
                                header = table_header[i]
                                if header in row:
                                    v = row[header]
                                else:
                                    v = None
                                list_data.append(v)
                            json_data[rowidx] = list_data
                json_data = dumps(json_data)
                out = json_data
            else:
                out = None
            output_dict[colname] = out
            if delflag:
                del output_dict[shortcolname]
        return output_dict

    def make_result_level_columns(self):
        from ..consts import LEVELS

        if not self.db_path or not self.dbconn:
            return None, None
        self.result_level_columns = {}
        cursor = self.dbconn.cursor()
        for level in LEVELS.keys():
            q = f"select name from pragma_table_info('{level}') as tblinfo"
            cursor.execute(q)
            columns = [v[0] for v in cursor.fetchall()]
            if columns:
                self.result_level_columns[level] = columns


    def get_result_module_columns(self, module_name):
        from ..consts import LEVELS

        if not self.db_path or not self.dbconn:
            return None, None
        self.cursor = self.dbconn.cursor()
        for level in LEVELS.keys():
            q = "select name from pragma_table_info('{level}') as tblinfo"
            self.cursor.execute(q)
            columns = [v[0] for v in self.cursor.fetchall() if v[0].startswith(f"{module_name}__")]
            if columns:
                return level, columns
        return None, None

    def get_result_module_column(self, query_column_name):
        for level, column_names in self.result_level_columns.items():
            for column_name in column_names:
                if column_name == query_column_name:
                    return level, column_name
        return None, None

    def setup_input_columns(self):
        from ..consts import VARIANT
        from ..consts import GENE

        if not self.conf:
            return
        self.make_result_level_columns()
        self.input_columns = {}
        input_columns = self.conf.get("input_columns")
        requires = self.conf.get("requires")
        if input_columns:
            for input_column_name in input_columns:
                level, column_name = self.get_result_module_column(input_column_name)
                if level and column_name:
                    if not self.input_columns.get(level):
                        self.input_columns[level] = []
                    self.input_columns[level].append(column_name)
        elif requires:
            for module_name in requires:
                level, column_names = self.get_result_module_columns(module_name)
                if level and column_names:
                    if not self.input_columns.get(level):
                        self.input_columns[level] = []
                    self.input_columns[level].extend(column_names)
        else:
            self.input_columns = None
        if self.input_columns:
            if self.levelno == VARIANT:
                if "base__uid" not in self.input_columns["variant"]:
                    self.input_columns["variant"].append("base__uid")
                if "gene" in self.input_columns and "base__hugo" not in self.input_columns["variant"]:
                    self.input_columns["variant"].append("base__hugo")
            elif self.levelno == GENE and "base__hugo" not in self.input_columns["gene"]:
                self.input_columns["gene"].append("base__hugo")

    def setup_output_columns(self):
        if not self.conf:
            return
        output_columns = self.conf["output_columns"]
        for col in output_columns:
            if "table" in col and col["table"] == True:
                self.json_colnames.append(col["name"])
                self.table_headers[col["name"]] = []
                for h in col["table_header"]:
                    self.table_headers[col["name"]].append(h["name"])

    def run(self):
        from time import time, asctime, localtime
        from ..exceptions import ConfigurationError
        from ..exceptions import LoggerError
        from ..exceptions import SetupError


        if self.conf is None:
            raise ConfigurationError()
        if self.dbconn is None:
            raise SetupError(module_name=self.module_name)
        if self.logger is None:
            raise LoggerError()
        if not self.should_run_annotate:
            self.base_cleanup()
            return
        start_time = time()
        self.status_writer.queue_status_update(
            "status", "Started {} ({})".format(self.conf["title"], self.module_name)
        )
        self.logger.info("started: {0}".format(asctime(localtime(start_time))))
        self.base_setup()
        self.json_colnames = []
        self.table_headers = {}
        self.setup_input_columns()
        self.setup_output_columns()
        self.process_file()
        self.fill_categories()
        self.dbconn.commit()
        self.postprocess()
        self.base_cleanup()
        end_time = time()
        run_time = end_time - start_time
        self.logger.info("finished: {0}".format(asctime(localtime(end_time))))
        self.logger.info("runtime: {0:0.3f}".format(run_time))
        self.status_writer.queue_status_update(
            "status", "Finished {} ({})".format(self.conf["title"], self.module_name)
        )

    def process_file(self):
        from time import time 
        from ..exceptions import ConfigurationError

        if self.conf is None:
            raise ConfigurationError()
        if not self.dbconn:
            return
        lnum = 0
        last_status_update_time = time()
        for input_data in self._get_input():
            try:
                output_dict = self.annotate(input_data)
                if not output_dict:
                    continue
                output_dict = self.handle_legacy_data(output_dict)
                self.write_output(output_dict, input_data=input_data)
                cur_time = time()
                lnum += 1
                if lnum % 10000 == 0 or cur_time - last_status_update_time > 3:
                    self.status_writer.queue_status_update(
                        "status",
                        "Running {} ({}): row {}".format(
                            self.conf["title"], self.module_name, lnum
                        ),
                    )
                    last_status_update_time = cur_time
            except Exception as e:
                self._log_runtime_exception(input_data, e)

    def postprocess(self):
        pass

    def fill_categories(self):
        from ..exceptions import ConfigurationError
        from ..exceptions import SetupError
        from ..util.inout import ColumnDefinition


        if self.conf is None:
            raise ConfigurationError()
        if self.cursor is None:
            raise SetupError()
        for col_d in self.conf["output_columns"]:
            col_def = ColumnDefinition(col_d)
            if col_def.category not in ["single", "multi"]:
                continue
            col_name = col_def.name
            q = "select distinct {} from {}".format(col_name, self.level)
            self.cursor.execute(q)
            col_cats = []
            for r in self.cursor:
                col_cat_str = r[0] if r[0] is not None else ""
                for col_cat in col_cat_str.split(";"):
                    if col_cat not in col_cats:
                        col_cats.append(col_cat)
            col_cats.sort()
            col_def.categories = col_cats
            q = "update {}_header set col_def=? where col_name=?".format(self.level)
            self.cursor.execute(q, [col_def.get_json(), col_def.name])

    def write_output(self, output_dict, input_data=None, base__uid=None, base__hugo=None):
        from ..exceptions import ConfigurationError
        from ..exceptions import SetupError
        from oakvar.consts import VARIANT, GENE

        if self.conf is None:
            raise ConfigurationError()
        if self.level is None or self.cursor is None or self.cursor_w is None:
            raise SetupError()
        vals = []
        set_strs = []
        for col_def in self.conf["output_columns"]:
            col_name = col_def["name"]
            shortcol_name = col_name.split("__")[1]
            if shortcol_name in output_dict:
                val = output_dict[shortcol_name]
                if val is None:
                    continue
                vals.append(val)
                set_strs.append(f"{col_name}=?")
        if len(vals) == 0:
            return
        set_str = ", ".join(set_strs)
        q = f"update {self.level} set {set_str} where "
        if self.levelno == VARIANT:
            q += "base__uid=?"
            if input_data:
                vals.append(input_data["base__uid"])
            elif base__uid:
                vals.append(base__uid)
            else:
                return
        elif self.levelno == GENE:
            q += 'base__hugo=?'
            if input_data:
                vals.append(input_data["base__hugo"])
            elif base__hugo:
                vals.append(base__hugo)
            else:
                return
        self.cursor_w.execute(q, vals)

    def _log_runtime_exception(self, input_data, e):
        if self.unique_excs is None:
            from ..exceptions import SetupError

            raise SetupError()
        if self.logger is None or self.error_logger is None:
            from ..exceptions import LoggerError

            raise LoggerError(module_name=self.module_name)
        import traceback

        try:
            err_str = traceback.format_exc().rstrip()
            if err_str not in self.unique_excs:
                self.unique_excs.append(err_str)
                self.logger.error(err_str)
            self.error_logger.error(f"{input_data[0]}\t{str(e)}")
            # self.error_logger.error(
            #    "\nINPUT:{}\nERROR:{}\n#".format(str(input_data), str(e))
            # )
        except Exception as e:
            self._log_exception(e, halt=False)

    # Setup function for the base_annotator, different from self.setup()
    # which is intended to be for the derived annotator.
    def base_setup(self):
        self._alter_tables()
        self.setup()

    def _open_db_connection(self):
        from sqlite3 import connect
        import os
        from ..exceptions import SetupError

        if self.db_path is None:
            raise SetupError()
        if os.path.exists(self.db_path):
            self.dbconn = connect(self.db_path)
            self.cursor = self.dbconn.cursor()
            self.cursor_w = self.dbconn.cursor()
            self.cursor_w.execute('pragma journal_mode="wal"')
        else:
            msg = str(self.db_path) + " not found"
            if self.logger:
                self.logger.error(msg)
            import sys

            sys.exit(msg)

    def _close_db_connection(self):
        if self.cursor is not None:
            self.cursor.close()
        if self.cursor_w is not None:
            self.cursor_w.close()
        if self.dbconn is not None:
            self.dbconn.close()

    def _alter_tables(self):
        if (
            self.level is None
            or self.conf is None
            or self.dbconn is None
            or self.cursor is None
            or self.cursor_w is None
        ):
            from ..exceptions import SetupError

            raise SetupError()
        from ..util.inout import ColumnDefinition

        # annotator table
        q = 'insert or replace into {:} values ("{:}", "{:}", "{}")'.format(
            self.level + "_annotator",
            self.module_name,
            self.conf["title"],
            self.conf["version"],
        )
        self.cursor_w.execute(q)
        # data table and header table
        header_table_name = self.level + "_header"
        for col_d in self.conf["output_columns"]:
            col_def = ColumnDefinition(col_d)
            colname = col_def.name
            coltype = col_def.type
            # data table
            try:
                self.cursor.execute(f"select {colname} from {self.level} limit 1")
            except:
                if coltype is not None:
                    q = (
                        "alter table "
                        + self.level
                        + " add column "
                        + colname
                        + " "
                        + self.cr_type_to_sql[coltype]
                    )
                    self.cursor_w.execute(q)
            # header table
            # use prepared statement to allow " characters in colcats and coldesc
            q = "insert or replace into {} values (?, ?)".format(header_table_name)
            self.cursor_w.execute(q, [colname, col_def.get_json()])
        self.dbconn.commit()

    # Placeholder, intended to be overridded in derived class
    def setup(self):
        pass

    def base_cleanup(self):
        self.cleanup()
        if self.dbconn != None:
            self._close_db_connection()

    def cleanup(self):
        pass

    def _setup_logger(self):
        import logging

        try:
            self.logger = logging.getLogger("oakvar." + self.module_name)
        except Exception as e:
            self._log_exception(e)
        self.error_logger = logging.getLogger("err." + self.module_name)
        self.unique_excs = []

    def columns_to_columns_str(self, columns):
        return ",".join(columns)

    def _get_input(self):
        from sqlite3 import connect
        from ..exceptions import SetupError
        from ..consts import VARIANT
        from ..consts import GENE

        if self.db_path is None or self.level is None or not self.dbconn:
            raise SetupError()
        conn = connect(self.db_path)
        c_var = self.dbconn.cursor()
        c_gen = self.dbconn.cursor()
        columns_v = None
        columns_g = None
        from_v = None
        from_g = None
        where_v = None
        where_g = None
        q_v = None
        q_g = None
        if not self.input_columns:
            if self.levelno == VARIANT:
                from_v = f"variant as v, gene as g"
                where_v = "v.base__hugo==g.base__hugo"
                columns_v = ["*"]
            elif self.levelno == GENE:
                from_g = f"gene as g"
                columns_v = ["*"]
        else:
            if self.levelno == VARIANT:
                if "gene" in self.result_level_columns:
                    from_v = "variant as v, gene as g"
                    where_v = "v.base__hugo==g.base__hugo"
                else:
                    from_v = "variant as v"
                columns = []
                for level, column_names in self.result_level_columns.items():
                    if level == "variant":
                        prefix = "v"
                    elif level == "gene":
                        prefix = "g"
                    else:
                        raise Exception(f"Unknown column level: {level} for {column_names}")
                    columns.extend([f"{prefix}.{column_name}" for column_name in column_names if column_name in self.input_columns[level]])
                columns_v = [column for column in columns]
            elif self.levelno == GENE:
                from_g = "gene as g"
                if "variant" in self.result_level_columns:
                    from_v = "variant as v"
                    where_v = "v.base__hugo=?"
                for level, column_names in self.result_level_columns.items():
                    if level == "variant":
                        prefix = "v"
                        columns_v = [f"{prefix}.{column_name}" for column_name in column_names if column_name in self.input_columns[level]]
                    elif level == "gene":
                        prefix = "g"
                        columns_g = [f"{prefix}.{column_name}" for column_name in column_names if column_name in self.input_columns[level]]
                    else:
                        raise Exception(f"Unknown column level: {level} for {column_names}")
            else:
                raise Exception(f"Unknown module level: {self.level} for {self.module_name}")
        if self.levelno == VARIANT:
            q_v = f"select {self.columns_to_columns_str(columns_v)} from {from_v}"
            if where_v:
                q_v += f" where {where_v}"
            c_var.execute(q_v)
            cursor = c_var
        elif self.levelno == GENE:
            q_g = f"select {self.columns_to_columns_str(columns_g)} from {from_g}"
            if where_g:
                q_g += f" where {where_g}"
            c_gen.execute(q_g)
            cursor = c_gen
            if columns_v:
                q_v = f"select {self.columns_to_columns_str(columns_v)} from {from_v}"
                if where_v:
                    q_v += f" where {where_v}"
        else:
            raise Exception(f"Unknown module level: {self.level} for {self.module_name}")
        for row in cursor:
            try:
                input_data = {}
                for i in range(len(row)):
                    input_data[cursor.description[i][0]] = row[i]
                if self.levelno == GENE and q_v and columns_v:
                    for column_name in columns_v:
                        input_data[column_name[2:]] = []
                    c_var.execute(q_v, (input_data["base__hugo"],))
                    sub_rows = c_var.fetchall()
                    for sub_row in sub_rows:
                        for i in range(len(sub_row)):
                            input_data[c_var.description[i][0]].append(sub_row[i])
                yield input_data
            except Exception as e:
                self._log_runtime_exception(row, e)
        cursor.close()
        if c_var:
            c_var.close()
        if c_gen:
            c_gen.close()
        conn.close()

    def annotate(self, __input_data__):
        raise NotImplementedError()
