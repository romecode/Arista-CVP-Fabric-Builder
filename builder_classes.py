import cvp
import urllib3
import datetime
import sys

#########PRINT LOGS#########
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class Log():
    def __init__(self, CONFIG):
        self.fabric_builder_log = open(CONFIG['fabric_builder_log'], 'a')
        
    def log_error(self,error_string):
        error_string = "{0]: {1}"%( datetime.datetime.now() + error_string )
        sys.stderr.write(error_string)
        self.error_log.write(error_string)
        

class Cvp():
    def __init__(self, CONFIG):
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # to supress the warnings for https
            self.connection = cvp.Cvp( CONFIG['cvp_server'] )
            self.connection.authenticate(CONFIG['cvp_user'], CONFIG['cvp_pass'])
        except:
            LOGGER.log_error("Unable to connect to CVP Server")
            sys.exit(0)
        
class Task():
    def __init__(self):
        self.name   = None
        self.config = []
        self.configletType = None
        self.device = None
        pass

class Switch():

    def __init__(self, params={}, cvpDevice = None):
        self.serial     = None
        self.model      = None
        self.hostname   = None
        self.container  = None
        self.management = None
        self.asn        = None
        self.lo0        = None
        self.lo1        = None
        self.cvp        = None
        self.todo       = []
        
        if cvpDevice:
            self.cvp = cvpDevice
        #else:
        for key, value in params.items():
            try:
                setattr(self, key, value)
            except:
                print "Switch init error on {0}:{1}".format(key,value)
                continue
            
        
class Manager():
    
    def __init__(self, CONFIG, CVP):
        self.switches = {}
        undefined  = [ d for d in CVP.connection.getDevices() ]
        
        with open("fabric_parameters.csv") as f:
            reader = csv.reader(f)
            headers = next(reader)
            #row[0] is the serial
            #passing a dict to the switch to preserve csv headers
            for row in reader:
                self.switches[row[0]] = Switch(dict(zip(headers,row)))
        
    def init_switch(self, params):
        #load from cvp data
        if isinstance(params, cvp.Device):
            pass
        #dict init
        elif isinstance(params, dict):
            pass
            