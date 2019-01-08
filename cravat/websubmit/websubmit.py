import os
import time
import datetime
import subprocess
import yaml
import json
from cravat import admin_util as au
from cravat import ConfigLoader
import sys
import traceback
import shutil
from aiohttp import web
#from cryptography import fernet
#from aiohttp_session import get_session, new_session
import sqlite3
import hashlib
from distutils.version import LooseVersion
import glob

class FileRouter(object):

    def __init__(self):
        self.root = os.path.dirname(__file__)
        self.input_fname = 'input'
        self.report_extensions = {
            'text':'.tsv',
            'excel':'.xlsx'
        }
        self.db_extension = '.sqlite'
        self.log_extension = '.log'

    async def get_jobs_dir (self, request):
        root_jobs_dir = au.get_jobs_dir()
        username = 'default'
        jobs_dir = os.path.join(root_jobs_dir, username)
        return jobs_dir

    async def job_dir(self, request, job_id):
        jobs_dir = await self.get_jobs_dir(request)
        if jobs_dir == None:
            return None
        else:
            return os.path.join(jobs_dir, job_id)

    async def job_input(self, request, job_id):
        jobs_dir = await self.job_dir(request, job_id)
        return os.path.join(jobs_dir, self.input_fname)

    async def job_db(self, request, job_id):
        output_fname = self.input_fname+self.db_extension
        jobs_dir = await self.job_dir(request, job_id)
        return os.path.join(jobs_dir, output_fname)

    async def get_job_orig_input_fname (request, job_id):
        job_dir = await self.job_dir(request, job_id)
        fns = os.listdir(job_dir)
        orig_input_fname = None
        for fn in fns:
            if fn.endswith('.status.json'):
                with open(os.path.join(job_dir, fn)) as f:
                    statusjson = json.loads(f.readline())
                    if 'orig_input_fname' in statusjson:
                        orig_input_fname = statusjson['orig_input_fname']
            elif fn.endswith('.info.yaml'):
                with open(os.path.join(job_dir, fn)) as f:
                    infojson = yaml.load(f)
                    if 'orig_input_fname' in infojson:
                        orig_input_fname = infojson['orig_input_fname']
        return os.path.join(job_dir, orig_input_fname)

    async def job_report(self, request, job_id, report_type):
        ext = self.report_extensions.get(report_type, '.'+report_type)
        orig_input_fname = await self.get_job_orig_input_fname(request, job_id)
        report_fname = orig_input_fname + ext
        return report_fname

    async def job_status_file(self, request, job_id):
        status_fname = 'input.status.json'
        jobs_dir = await self.job_dir(request, job_id)
        return os.path.join(jobs_dir, status_fname)

    async def job_status (self, request, job_id):
        job_dir = await self.job_dir(request, job_id)
        fns = os.listdir(job_dir)
        statusjson = {}
        for fn in fns:
            if fn.endswith('.status.json'):
                with open(os.path.join(job_dir, fn)) as f:
                    statusjson = json.loads(f.readline())
            elif fn.endswith('.info.yaml'):
                with open(os.path.join(job_dir, fn)) as f:
                    statusjson = yaml.load(f)
        return statusjson
        
    async def job_log(self, request, job_id):
        orig_input_fname = self.get_job_orig_input_fname(request, job_id)
        if orig_input_fname is not None:
            log_fname = orig_input_fname + '.log'
            if os.path.exists(log_fname) == False:
                log_fname = None
        else:
            log_fname = None
        return log_fname

class WebJob(object):
    def __init__(self, job_dir, job_status_fpath):
        self.info = {}
        self.job_dir = job_dir
        self.job_status_fpath = job_status_fpath
        self.info['id'] = os.path.basename(job_dir)

    def save_job_options (self, job_options):
        self.set_values(**job_options)

    def read_info_file(self):
        with open(self.job_status_fpath) as f:
            info_dict = yaml.load(f)
        if info_dict != None:
            self.set_values(**info_dict)

    def set_info_values(self, **kwargs):
        self.set_values(**kwargs)

    def get_info_dict(self):
        return self.info

    def set_values(self, **kwargs):
        self.info.update(kwargs)

def get_next_job_id():
    return datetime.datetime.now().strftime(r'%y%m%d-%H%M%S')

async def submit (request):
    global filerouter
    reader = await request.multipart()
    input_file = None
    job_options = None
    while True:
        part = await reader.next()
        if not part: 
            break 
        if part.name == 'file':
            input_file = part
            input_data = await input_file.read()
        elif part.name == 'options':
            job_options = await part.json()
        if input_file is not None and job_options is not None: 
            break
    orig_input_fname = input_file.filename
    job_id = get_next_job_id()
    jobs_dir = await filerouter.get_jobs_dir(request)
    job_dir = os.path.join(jobs_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)
    info_fname = '{}.status.json'.format(orig_input_fname)
    job_info_fpath = os.path.join(job_dir, info_fname)
    job = WebJob(job_dir, job_info_fpath)
    job.save_job_options(job_options)
    input_fpath = os.path.join(job_dir, orig_input_fname)
    with open(input_fpath, 'wb') as wf:
        wf.write(input_data)
    job.set_info_values(orig_input_fname=orig_input_fname,
                        submission_time=datetime.datetime.now().isoformat(),
                        viewable=False
                        )
    # Subprocess arguments
    run_args = ['cravat',
                input_fpath]
    # Annotators
    if len(job_options['annotators']) > 0:
        run_args.append('-a')
        run_args.extend(job_options['annotators'])
    else:
        run_args.append('--sa')
        run_args.append('-e')
        run_args.append('*')
    # Liftover assembly
    run_args.append('-l')
    run_args.append(job_options['assembly'])
    # Reports
    if len(job_options['reports']) > 0:
        run_args.append('-t')
        run_args.extend(job_options['reports'])
    else:
        run_args.append('--sr')
    p = subprocess.Popen(run_args)
    status = {'status': 'Submitted'}
    job.set_info_values(status=status)
    # admin.sqlite
    if servermode:
        root_jobs_dir = au.get_jobs_dir()
        admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
        db = sqlite3.connect(admin_db_path)
        cursor = db.cursor()
        '''
        session = await get_session(request)
        username = session['username']
        '''
        username = 'default'
        cursor.execute('insert into jobs values ("{}", "{}", "{}", {}, {}, "{}", "{}")'.format(job_id, username, job.get_info_dict()['submission_time'], -1, -1, '', job_options['assembly']))
        db.commit()
    return web.json_response(job.get_info_dict())

def get_annotators(request):
    out = {}
    for local_info in au.get_local_module_infos(types=['annotator']):
        module_name = local_info.name
        if local_info.type == 'annotator':
            out[module_name] = {
                                'name':module_name,
                                'version':local_info.version,
                                'type':local_info.type,
                                'title':local_info.title,
                                'description':local_info.description,
                                'developer': local_info.developer
                                }
    return web.json_response(out)

def find_files_by_ending (d, ending):
    fns = os.listdir(d)
    files = []
    for fn in fns:
        if fn.endswith(ending):
            files.append(fn)
    return files

async def get_all_jobs (request):
    global filerouter
    jobs_dir = await filerouter.get_jobs_dir(request)
    if jobs_dir == None:
        return web.json_response([])
    if os.path.exists(jobs_dir) == False:
        os.mkdir(jobs_dir)
    ids = os.listdir(jobs_dir)
    ids.sort(reverse=True)
    all_jobs = []
    for job_id in ids:
        try:
            job_dir = os.path.join(jobs_dir, job_id)
            if os.path.isdir(job_dir) == False:
                continue
            fns = find_files_by_ending(job_dir, '.status.json')
            if len(fns) < 1:
                continue
            status_fname = fns[0]
            status_fpath = os.path.join(job_dir, status_fname)
            job = WebJob(job_dir, status_fpath)
            job.read_info_file()
            fns = find_files_by_ending(job_dir, '.info.yaml')
            if len(fns) > 0:
                info_fpath = os.path.join(job_dir, fns[0])
                with open (info_fpath) as f:
                    info_json = yaml.load('\n'.join(f.readlines()))
                    for k, v in info_json.items():
                        if k == 'status' and 'status' in job.info:
                            continue
                        job.info[k] = v
            fns = find_files_by_ending(job_dir, '.sqlite')
            if len(fns) > 0:
                db_path = os.path.join(job_dir, fns[0])
            else:
                db_path = ''
            job_viewable = os.path.exists(db_path)
            job.set_info_values(
                viewable=job_viewable,
                db_path=db_path,
                status=job.info['status'],
            )
            existing_reports = []
            for report_type in get_valid_report_types():
                ext = filerouter.report_extensions.get(report_type, '.'+report_type)
                report_fname = job.info['orig_input_fname'] + ext
                report_file = os.path.join(job_dir, report_fname)
                if os.path.exists(report_file):
                    existing_reports.append(report_type)
            job.set_info_values(reports=existing_reports)
            all_jobs.append(job)
        except:
            traceback.print_exc()
            continue
    return web.json_response([job.get_info_dict() for job in all_jobs])

async def view_job(request):
    global VIEW_PROCESS
    global filerouter
    job_id = request.match_info['job_id']
    db_path = await filerouter.job_db(request, job_id)
    if os.path.exists(db_path):
        if type(VIEW_PROCESS) == subprocess.Popen:
            VIEW_PROCESS.kill()
        VIEW_PROCESS = subprocess.Popen(['cravat-view', db_path])
        return web.Response()
    else:
        return web.Response(status=404)

async def delete_job(request):
    global filerouter
    job_id = request.match_info['job_id']
    job_dir = await filerouter.job_dir(request, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)
        return web.Response()
    else:
        return web.Response(status=404)

async def download_db(request):
    global filerouter
    job_id = request.match_info['job_id']
    db_path = await filerouter.job_db(request, job_id)
    db_fname = job_id+'.sqlite'
    headers = {'Content-Disposition': 'attachment; filename='+db_fname}
    return web.FileResponse(db_path, headers=headers)

async def get_job_log (request):
    global filerouter
    job_id = request.match_info['job_id']
    log_path = await filerouter.job_log(request, job_id)
    if log_path is not None:
        with open(log_path) as f:
            return web.Response(text=f.read())
    else:
        return web.Response(text='loo file does not exist.')

def get_valid_report_types():
    reporter_infos = au.get_local_module_infos(types=['reporter'])
    report_types = [x.name.split('reporter')[0] for x in reporter_infos]
    return report_types

def get_report_types(request):
    cfl = ConfigLoader()
    default_reporter = cfl.get_cravat_conf_value('reporter')
    default_type = default_reporter.split('reporter')[0]
    valid_types = get_valid_report_types()
    return web.json_response({'valid': valid_types, 'default': default_type})

async def generate_report(request):
    global filerouter
    job_id = request.match_info['job_id']
    statusjson = await filerouter.job_status(request, job_id)
    report_type = request.match_info['report_type']
    if report_type in get_valid_report_types():
        job_input = statusjson['orig_input_path']
        cmd_args = ['cravat', job_input]
        cmd_args.append('--str')
        cmd_args.extend(['-t', report_type])
        p = subprocess.Popen(cmd_args)
        p.wait()
    return web.Response()

async def download_report(request):
    global filerouter
    job_id = request.match_info['job_id']
    report_type = request.match_info['report_type']
    report_path = await filerouter.job_report(request, job_id, report_type) 
    report_name = job_id+'.'+report_path.split('.')[-1]
    headers = {'Content-Disposition':'attachment; filename='+report_name}
    return web.FileResponse(report_path, headers=headers)

def get_jobs_dir (request):
    jobs_dir = au.get_jobs_dir()
    return web.json_response(jobs_dir)

def set_jobs_dir (request):
    queries = request.rel_url.query
    d = queries['jobsdir']
    au.set_jobs_dir(d)
    return web.json_response(d)

async def get_system_conf_info (request):
    info = au.get_system_conf_info_json()
    global filerouter
    return web.json_response(info)

async def update_system_conf (request):
    queries = request.rel_url.query
    sysconf = json.loads(queries['sysconf'])
    try:
        success = au.update_system_conf_file(sysconf)
    except:
        raise
        sysconf = {}
        success = False
    return web.json_response({'success': success, 'sysconf': sysconf})

def reset_system_conf (request):
    d = au.read_system_conf_template()
    md = au.get_modules_dir()
    jobs_dir = au.get_jobs_dir()
    d['modules_dir'] = md
    d['jobs_dir'] = jobs_dir
    au.write_system_conf_file(d)
    return web.json_response({'status':'success', 'dict':yaml.dump(d)})

async def create_user_dir (request, username):
    global filerouter
    jobs_dir = await filerouter.get_jobs_dir(request)
    if os.path.exists(jobs_dir) == False:
        os.mkdir(jobs_dir)

async def signup (request):
    #session = await new_session(request)
    queries = request.rel_url.query
    username = queries['username']
    password = queries['password']
    m = hashlib.sha256()
    m.update(password.encode('utf-16be'))
    passwordhash = m.hexdigest()
    question = queries['question']
    answer = queries['answer']
    m = hashlib.sha256()
    m.update(answer.encode('utf-16be'))
    answerhash = m.hexdigest()
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    cursor.execute('select * from users where email="{}"'.format(username))
    r = cursor.fetchone()
    if r is not None:
        return web.json_response('already registered')
    cursor.execute('insert into users values ("{}", "{}", "{}", "{}")'.format(username, passwordhash, question, answerhash))
    cursor.close()
    db.commit()
    db.close()
    '''
    session['username'] = username
    session['logged'] = True
    '''
    await create_user_dir(request, username)
    return web.json_response('success')

async def login (request):
    #session = await new_session(request)
    queries = request.rel_url.query
    username = queries['username']
    password = queries['password']
    m = hashlib.sha256()
    m.update(password.encode('utf-16be'))
    passwordhash = m.hexdigest()
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    cursor.execute('select * from users where email="{}" and passwordhash="{}"'.format(username, passwordhash))
    r = cursor.fetchone()
    if r is not None:
        response = 'success'
        '''
        session['username'] = username
        session['logged'] = True
        '''
        await create_user_dir(request, username)
    else:
        response = 'fail'
    return web.json_response(response)

async def get_password_question (request):
    #session = await get_session(request)
    queries = request.rel_url.query
    email = queries['email']
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    cursor.execute('select question from users where email="{}"'.format(email))
    r = cursor.fetchone()
    if r is None:
        return web.json_response({'status':'fail', 'msg':'No such email'})
    answer = r[0]
    return web.json_response({'status':'success', 'msg':answer})

async def check_password_answer (request):
    #session = await get_session(request)
    queries = request.rel_url.query
    email = queries['email']
    answer = queries['answer']
    m = hashlib.sha256()
    m.update(answer.encode('utf-16be'))
    answerhash = m.hexdigest()
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    cursor.execute('select * from users where email="{}" and answerhash="{}"'.format(email, answerhash))
    r = cursor.fetchone()
    if r is not None:
        temppassword = 'open_cravat_temp_password'
        m = hashlib.sha256()
        m.update(temppassword.encode('utf-16be'))
        temppasswordhash = m.hexdigest()
        cursor.execute('update users set passwordhash="{}" where email="{}"'.format(temppasswordhash, email))
        db.commit()
        return web.json_response({'success': True, 'msg': temppassword})
    else:
        return web.json_response({'success': False, 'msg': 'Wrong answer'})

async def change_password (request):
    '''
    session = await get_session(request)
    email = session['username']
    '''
    email = 'default'
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    queries = request.rel_url.query
    oldpassword = queries['oldpassword']
    newpassword = queries['newpassword']
    m = hashlib.sha256()
    m.update(oldpassword.encode('utf-16be'))
    oldpasswordhash = m.hexdigest()
    cursor.execute('select * from users where email="{}" and passwordhash="{}"'.format(email, oldpasswordhash))
    r = cursor.fetchone()
    if r is None:
        return web.json_response('User authentication failed.')
    else:
        m = hashlib.sha256()
        m.update(newpassword.encode('utf-16be'))
        newpasswordhash = m.hexdigest()
        cursor.execute('update users set passwordhash="{}" where email="{}"'.format(newpasswordhash, email))
        db.commit()
        return web.json_response('success')

async def check_logged (request):
    '''
    session = await get_session(request)
    username = session['username']
    logged = session['logged']
    '''
    username = 'default'
    logged = False
    if logged:
        return web.json_response({'logged': True, 'email': username})
    else:
        return web.json_response({'logged': False, 'email': ''})

async def logout (request):
    '''
    session = await new_session(request)
    session['username'] = None
    '''
    return web.json_response('success')
    '''
    username = session['username']
    root_jobs_dir = au.get_jobs_dir()
    admin_db_path = os.path.join(root_jobs_dir, 'admin.sqlite')
    db = sqlite3.connect(admin_db_path)
    cursor = db.cursor()
    cursor.execute('select * from users where email="{}" and passwordhash="{}"'.format(username, passwordhash))
    r = cursor.fetchone()
    if r is not None:
        response = 'success'
        session['username'] = username
        session['logged'] = True
        await create_user_dir(request, username)
    else:
        response = 'fail'
    return web.json_response(response)
    '''

def get_servermode (request):
    return web.json_response({'servermode': servermode})

async def get_package_versions(request):
    cur_ver = au.get_current_package_version()
    lat_ver = au.get_latest_package_version()
    update = LooseVersion(lat_ver) > LooseVersion(cur_ver)
    d = {
        'current': cur_ver,
        'latest': lat_ver,
        'update': update
    }
    return web.json_response(d)


filerouter = FileRouter()
VIEW_PROCESS = None

routes = []
routes.append(['POST','/submit/submit',submit])
routes.append(['GET','/submit/annotators',get_annotators])
routes.append(['GET','/submit/jobs',get_all_jobs])
routes.append(['GET','/submit/jobs/{job_id}',view_job])
routes.append(['DELETE','/submit/jobs/{job_id}',delete_job])
routes.append(['GET','/submit/jobs/{job_id}/db', download_db])
routes.append(['GET','/submit/reports',get_report_types])
routes.append(['POST','/submit/jobs/{job_id}/reports/{report_type}',generate_report])
routes.append(['GET','/submit/jobs/{job_id}/reports/{report_type}',download_report])
routes.append(['GET','/submit/jobs/{job_id}/log',get_job_log])
routes.append(['GET', '/submit/getjobsdir', get_jobs_dir])
routes.append(['GET', '/submit/setjobsdir', set_jobs_dir])
routes.append(['GET', '/submit/getsystemconfinfo', get_system_conf_info])
routes.append(['GET', '/submit/updatesystemconf', update_system_conf])
routes.append(['GET', '/submit/resetsystemconf', reset_system_conf])
routes.append(['GET', '/submit/login', login])
routes.append(['GET', '/submit/servermode', get_servermode])
routes.append(['GET', '/submit/signup', signup])
routes.append(['GET', '/submit/logout', logout])
routes.append(['GET', '/submit/passwordquestion', get_password_question])
routes.append(['GET', '/submit/passwordanswer', check_password_answer])
routes.append(['GET', '/submit/changepassword', change_password])
routes.append(['GET', '/submit/checklogged', check_logged])
routes.append(['GET', '/submit/packageversions', get_package_versions])

if __name__ == '__main__':
    app = web.Application()
    for route in routes:
        method, path, func_name = route
        app.router.add_route(method, path, func_name)
    web.run_app(app, port=8060)
