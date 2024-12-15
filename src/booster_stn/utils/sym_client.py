import urllib
import urllib.request
import json, os
import numpy as np, pandas as pd

URL_POST = '/api/actions/json' # URL for POST calls
URL_GET = '/api/values' # URL for GET calls

class SymClient(object):
    
    '''
    Client to generate API requests to Symmetry server.
    Requires:
        case_path: Path of the Symmetry case
        host: Host for the URI, typically localhost if running locally
        port: Port for the URI, port 80 is used by default
    '''
    
    def __init__(self, case_path, host='localhost', port=80):
        
        self.case_path = case_path
        self.port = port
        self.host = host

    ### API requests

    def SymmetryURL(self, callType=URL_POST):
        ''' URL changes based on the type of call '''
        return 'http://' + str(self.host) + ':' + str(self.port) + callType

    def POST_ToSymmetry(self, jsonData={}):
        ''' POST call to Symmetry '''
        
        encoding = 'utf-8'
        
        jdata = json.dumps(jsonData)
        jdata = jdata.encode(encoding)
        
        req = urllib.request.Request(self.SymmetryURL(), data=jdata, headers={'Content-Type':'application/json'})
        response = b''
        with urllib.request.urlopen(req) as _response:
            readVal = _response.read()
            response += readVal
        response = response.decode(encoding)
        
        return response

    ### Run Tasks
    
    def SolveCaseStudy(self, ind, dep, idx=None, preSolveCmds=[]):

        '''
        Recalls Symmetry case and runs a case study.

        Requires the case path, independent and dependent variables.

        Pre-solve commands can be modified to change a variable value before
        starting the case study.
        
        '''
        
        results = pd.DataFrame()

        dep_vars = []
        dep_map = {}
        for var in dep:
            dep_vars.append(var['path'])
            dep_map[var['path']] = f"{var['label']} ({var['unit']})"

        ind_vars = []
        for var in ind:
            indep_var = {
                "p": var['path'],
                "vals": var['vals'],
                "u": var['unit']
            }
            ind_vars.append(indep_var)
            results[f"{var['label']} ({var['unit']})"] = var['vals']


        # Set up case study
        case_study = {
            "call": "RunCaseStudy",
            "args": {
                "casePath": self.case_path,
                "caseStudy": {
                    "n": "CaseStudy1",
                    "indVars": ind_vars,
                    "depVars": dep_vars,
                },
                "logToCsv":           False,
                "logExtraStreamData": False,
                "preSolveCmds": preSolveCmds,
                "postSolveCmds": [],
                "runAllCombinations": False
            }
        }
    
        response = self.POST_ToSymmetry(case_study)
        response = json.loads(response)

        if response['status'] != 0:
            raise RuntimeError(response['msg'])
        
        res = response['resp']['caseStudy']['results']
        
        for r in res:
            label = dep_map.get(r['p'])
            if label:
                results[label] = r['vals']

        if idx:
            results.set_index([pd.Index(idx)], inplace=True)

        return results
    
if __name__ == '__main__':
    pass