import urllib
import urllib.request
import json, os


SYM_CASE = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'case', 'case.vsym'))

URL_POST = '/api/actions/json' # URL for POST calls
URL_GET = '/api/values' # URL for GET calls

class SymClient(object):

    def __init__(self, host='localhost', port=8080):
        
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

    ### Make JSON message
        
    def SolveCase(self, preSolveCmds=[], postSolveCmds=[]):

        ''' Recall and solve a Symmetry case.
            If reportMode is set to "specs", the SolveCase
            API call returns all case specs afetr solve.
        '''
        
        msg = {}

        msg['call'] = "SolveCase"
        msg['args'] = {}
        msg['args']['casePath'] = SYM_CASE
        msg['args']['preSolveCmds'] = preSolveCmds
        msg['args']['postSolveCmds'] = postSolveCmds
        msg['args']['reportMode'] = 'none'

        _response = self.POST_ToSymmetry(jsonData=msg)
        
        response = json.loads(_response)

        return response

    #### Run task

    def MakePreSolveCmd(self, paths, vals, units=[], solve=1):
        ''' Set values (actions) '''

        msg = {}
        msg['call'] = 'SetValues'
        
        setArgs = []
        for i in range(len(paths)):
            setArg = {}
            setArg['p'] = paths[i]
            setArg['val'] = vals[i]
            if len(units):
                setArg['u'] = units[i]

            setArgs.append(setArg)
        
        msg['args'] = {'vals': setArgs, 'solve': solve}

        return [msg]

    def MakePostSolveCmd(self, paths, units=[]):
        ''' Get values (rewards) '''

        msg = {}
        msg['call'] = 'Variables'
        
        reqVars = []
        for i in range(len(paths)):
            getArg = {}
            getArg['p'] = paths[i]
            if len(units):
                getArg['u'] = units[i]
            reqVars.append(getArg)
        
        msg['args'] = {'reqVars': reqVars}

        return [msg]

    def RunTask(self, setPaths, setVals, getPaths, setUnits=[], getUnits=[]):
        
        preSolveCmds = self.MakePreSolveCmd(setPaths, setVals, units=setUnits)
        postSolveCmds = self.MakePostSolveCmd(getPaths, units=getUnits)

        response = self.SolveCase(preSolveCmds=preSolveCmds,
                            postSolveCmds=postSolveCmds)
        if response['status'] == 0:
            return response['resp']['postSolveOut'][0]['resp']
        return response['msg']
    
    def solve_case(self):

        set_thermo_cmds = [
            '$VMGThermo + NITROGEN',
            '$VMGThermo + CARBON_DIOXIDE',
            '$VMGThermo + METHANE',
            '$VMGThermo + ETHANE',
            '$VMGThermo + PROPANE',
            '$VMGThermo + ISOBUTANE',
            '$VMGThermo + n-BUTANE',
            '$VMGThermo + ISOPENTANE',
            '$VMGThermo + n-PENTANE',
            '''$VMGThermo.C6+* = HypoCompound """
            MolecularWeight = 98
            LiquidDensity@298 = 611.9
            """''',
            '$VMGThermo + WATER',
            '$VMGThermo + ETHYLENE_GLYCOL',
           ' $VMGThermo + METHANOL',
            "/S1 = Stream.Stream_Material()",
            "'/S1.In.T' = 68 F",
            "'/S1.In.P' = 80 psia",
            "'/S1.In.MoleFlow' = 1",
            "'/S1.In.Fraction' =  0.004374 0.018034 0.733803 0.122776 0.067194 0.008483 0.025605 0.006355 0.008306 0.00507 0 0 0"
        ]
        
        msg = {
            "call": "SolveCase",
            "args": {
                "casePath": "D:/dev/_Symmetry/sym_thermo/model/sym_model.vsym",
                "preSolveCmds": set_thermo_cmds,
                "postSolveCmds": [
                {
                    "call": "Variables",
                    "args": {
                    "reqVars": [
                        { "p": "/S1.In.StdGasVolumeFlow" },
                        { "p": "/S1.In.Energy" }
                    ]
                    }
                }
                ],
                "reportMode": "specs"
            }
        }
        _response = self.POST_ToSymmetry(jsonData=msg)
        return _response

    def generic(self):
        actionPaths = ['/Sour_Gas.In.StdGasVolumeFlow',
                   '/Sour_Gas.In.T']
        actionVals = [1.0e6,
                        30.0]
        rewardsPaths = ['/Acid_Gas.In.StdGasVolumeFlow',
                        '/Sales_Gas.In.StdGasVolumeFlow']

        c = SymClient()
        resp = c.RunTask(actionPaths, actionVals, rewardsPaths)
        return resp
    

if __name__ == '__main__':

    sym = SymClient()
    resp = sym.solve_case()
    
    print(resp)
    
