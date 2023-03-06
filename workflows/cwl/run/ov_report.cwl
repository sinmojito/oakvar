cwlVersion: v1.2
class: CommandLineTool

baseCommand: ov

arguments: 
  - valueFrom: $(inputs.sqlite_file)
    prefix: report
  - valueFrom: excel
    prefix: -t
  - valueFrom: annotated
    prefix: -s
requirements:
  EnvVarRequirement:
    envDef:
      TMP: $(inputs.tmp)
      HOME: $(inputs.home) 

inputs: 
  sqlite_file:
    type: File
  home: string
  tmp: string
outputs:
  excel_file:
    type: File
    outputBinding:
      glob: "*.xlsx"