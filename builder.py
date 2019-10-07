#This should contain cli logic be the place of execution
import cmd
#pyeapi might be overkill
#import pyeapi
from jsonrpclib import Server 


import csv
from ConfigParser import SafeConfigParser
from collections import namedtuple
import urllib3
import cvp
import re

#need this to avoid ssl invalid cert bypass (at least on my mac it failed, pyeapi)
#only other way is to set env vars or modify .conf in /etc
import os, ssl
if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
    getattr(ssl, '_create_unverified_context', None)):
  ssl._create_default_https_context = ssl._create_unverified_context

DEBUG = True
LOGGER = None
CVP = None

#User which has access to switches via http and cvp
#should be a static config on the staging container
CONFIG = {}
TEMPLATES = {}
DEVICES = {}
SPINES = []

def getBySerial(sn):
    return DEVICES[sn]

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
    def __init__(self):
        self.fabric_builder_log = open('fabric_builder_log.txt', 'a')
        
    def log(self,string):
        string = "{0}: {1}\n".format( datetime.datetime.now(), string )
        sys.stderr.write(string)
        self.fabric_builder_log.write(string)
        

class Cvp():
    def __init__(self):
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # to supress the warnings for https
            self.connection = cvp.Cvp( CONFIG['cvp_server'] )
            self.connection.authenticate(CONFIG['cvp_user'], CONFIG['cvp_pass'])
            LOGGER.log("Successfully authenticated to CVP: Loading devices...")
            devices = self.connection.getDevices()
            self.devices = {devices[x].sn:devices[x] for x in range(len(devices))}
            
        except:
            LOGGER.log("Unable to connect to CVP Server")
            sys.exit(0)
            
    @property
    def undefined(self):
        return [ d.sn for k, v in self.devices.items() if v.containerName == 'Undefined' ]
    
    @property
    def deployed(self):
        return [ d.sn for k, v in self.devices.items() if v.containerName != 'Undefined' ]
    
    def getBySerial(self,sn):
        return self.devices.get(sn)
    
    def deployDevice(self, device):
        try:
            task_id = self.connection.deployDevice(device.cvp,device.mgmt-ip,device.container,device.configlet_list)
        except:
            LOGGER.log("Deploying device {0}: failed, could not get task id from CVP".format(device.sn))
        else:
            self.connection.executeTask(task_id)
            LOGGER.log("Deploying device {0}: {1} to {2} container with task id {3}".format(device.sn, device.mgmt_ip, device.container, task_id))
        
class Task():
    def __init__(self):
        self.name   = None
        self.config = []
        self.configletType = None
        self.device = None
        pass

class Switch():
    
    def __init__(self, params={}, cvpDevice=None):
        self.configlet_list = []
        
        for k, v in params.items():
            setattr(self, k, v)
            
        if cvpDevice:
            self.cvp = cvpDevice
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, 'x'))
        else:
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, ''))
            
    def compile_configlet(self, name, template):
        print template.compile(self)
        
class Manager():
    
    def __init__(self):
        global DEVICES
        global SPINES
        
        with open("fabric_parameters.csv") as f:
            reader = csv.reader(f)
            headers = [header.lower() for header in next(reader)]
            #row[0] is the serial
            #passing a dict to the switch to preserve csv headers
            for row in reader:
                sn = row[0]
                role_index = headers.index("role")
                
                DEVICES[sn] = Switch(dict(zip(headers,row)), CVP.getBySerial(sn))
                if row[role_index].lower() == "spine" or (CONFIG['spines'] and CONFIG['spines'].index(sn)):
                    SPINES.push(DEVICES[sn])
                    
def get_global_vars(object, option, related_config):
    translated_dict = {}
    for config in related_config:
        #for each config_var get the missing vars needed from global config
        related_config_vars = re.findall('\{\{(.*?)\}\}', getattr(object, config))
        
        #is defined globally?
        for item in related_config_vars:
            #check if dict already has defined
            if getattr(translated_dict, item, None):
                continue
            global_value = CONFIG.get(item, None)
            if not global_value:
                LOGGER.log("Skipping configlet option {0}: global definition for {1} undefined".format(option, item))
                return None
            translated_dict[item] = global_value
    return translated_dict


class Configlet():
    def __init__(self, name, params={}):        
        self.name = name
        for k, v in params.items():
            if k == 'options':
                v = v.split()
            setattr(self, k, v)
                
        #option will be vrf
        for option in self.options:
            #LOOK THROUGH ALL THE CONFIG_VARS AND FIND NEEDED GLOBAL VARS
            #this will hold the local variables e.g. vrf_definition which match the placeholders in configlet
            related_templates = [related_templ for related_templ in vars(self).keys() if related_templ.startswith(option)]
            translated_dict = get_global_vars(self, option, related_templates)
            if translated_dict != None:
                for template in related_templates:
                    for k,v in translated_dict.items():

                        setattr(self, template, re.sub("\{\{"+k+"\}\}", v, getattr(self, template)))
                    self.configlet = re.sub("\{"+template+"\}", getattr(self, template), self.configlet)

            else:
                #flush variables in configlet
                for template in related_templates:
                    
                    self.configlet = re.sub("\{"+template+"\}(.*?)\n?", '', self.configlet)

    
    
    
    def compile(self, device):
        return self.configlet
        
            
        
        

class FabricBuilder(cmd.Cmd):
    """Arista Fabric Initializer"""
    

    
    def do_test_configlet(self, line):
        sn, name = line.split(',')
        switch = getBySerial(sn)
        switch.compile_configlet(name, TEMPLATES[name])
        
    def do_teapi(self,ip):
        #PYEAPI
        #conn = pyeapi.connect(host=ip,username=CONFIG['cvp_user'],password=CONFIG['cvp_pass'])
        #print conn.execute(["show platform"])
        
        switch = Server( "https://{0}:{1}@10.20.30.23/command-api".format(CONFIG['cvp_user'],CONFIG['cvp_pass']) )
        response = switch.runCmds( 1, [ "show platform jericho" ], 'text' ) 
        print response
        
    def do_EOF(self, line):
        return True
    
def main():
    #TODO
    pass


def debug():
    global TEMPLATES
    
    #INIT CONFIG
    parser = SafeConfigParser()
    parser.read('fabric_builder_global.conf')
    for name, value in parser.items('global'):
        if name == 'spines':
            if value:
                value = value.split(',')
            else:
                value = []
        CONFIG[name] = value
        
    #INIT LOGGER
    global LOGGER
    LOGGER = Log()
    
    parser = SafeConfigParser()
    parser.read('fabric_builder_templates.conf')
    for section in parser.sections():
        TEMPLATES[section] = Configlet(section, dict(parser.items(section)))
        
    
    
    global CVP 
    CVP = Cvp()
    
    global MANAGER 
    MANAGER = Manager()

    FabricBuilder().cmdloop()

if __name__ == '__main__':
    if DEBUG:
        debug()
    else:
        main()
        
        

