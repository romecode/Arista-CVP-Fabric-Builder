#This should contain cli logic be the place of execution
import cmd
#pyeapi might be overkill
#import pyeapi
#from jsonrpclib import Server 
import csv
from ConfigParser import SafeConfigParser
from collections import OrderedDict
import urllib3
import cvp
import re
from ipaddress import ip_address
import os, ssl
import sys
import datetime
from macresource import need

#need this to avoid ssl invalid cert bypass (at least on my mac it failed, pyeapi)
#only other way is to set env vars or modify .conf in /etc
#===============================================================================
# if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
#     getattr(ssl, '_create_unverified_context', None)):
#   ssl._create_default_https_context = ssl._create_unverified_context
#===============================================================================


LOGGER = None
CVP = None
CONFIG = {}
TEMPLATES = {}
DEVICES = {}
HOST_TO_SN = {}
SPINES = []



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
            #urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # to supress the warnings for https
            #self.connection = cvp.Cvp( searchConfig('cvp_server') )
            #self.connection.authenticate(searchConfig('cvp_user'), searchConfig('cvp_pass') )
            #LOGGER.log("Successfully authenticated to CVP: Loading devices...")
            #devices = self.connection.getDevices()
            devices = {}
            self.devices = {devices[x].sn:devices[x] for x in range(len(devices))}
            
        except:
            LOGGER.log("Unable to connect to CVP Server")
            sys.exit(0)
    
    def getBySerial(self,sn):
        return self.devices.get(sn, None)
    
    def deployDevice(self, device):
        try:
            task_id = self.connection.deployDevice(device.cvp,device.mgmt-ip,device.container,device.configlet_list)
        except:
            LOGGER.log("Deploying device {0}: failed, could not get task id from CVP".format(device.sn))
        else:
            self.connection.executeTask(task_id)
            LOGGER.log("Deploying device {0}: {1} to {2} container with task id {3}".format(device.sn, device.mgmt_ip, device.container, task_id))
        
class Task():
    def __init__(self, device):
        self.device = device
    
    def execute(self):
        for item in self.device.to_deploy:
            print "************************************"
            print item[0]
            print "************************************"
            print item[1].compile(self.device)
        self.device.to_deploy = []
            

class Switch():
    
    def __init__(self, params={}, cvpDevice=None):
        #list to hold leaf compiled spine underlay interface init
        self.underlay_inject = []
        self.to_deploy = []
        for k, v in params.items():
            setattr(self, k, v.replace("|",","))
            
        if cvpDevice:
            self.cvp = cvpDevice
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, 'x'))
        else:
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, ''))
            
    def assign_configlet(self, template):
        #TODO: MAKE HANDLE LIST LOOKUPS, RIGHT NOW ONLY WORKS FOR ONE CONTAINER OR ONE DEVICE i.e. USELESS
        exception = getattr(template, "skip_container", None)
        if exception == self.role:
            return None
        exception = getattr(template, "skip_device", None)
        if exception == self.sn:
            return None
        configlet_name = "{0}-{1}-CONFIG".format(template.name.upper(), self.hostname.upper())
        self.to_deploy.append((configlet_name, template))
     
    def compile_configlet(self, template):
        #TODO: MAKE HANDLE LIST LOOKUPS, RIGHT NOW ONLY WORKS FOR ONE CONTAINER OR ONE DEVICE i.e. USELESS
        exception = getattr(template, "skip_container", None)
        if exception == self.role:
            return " "
        exception = getattr(template, "skip_device", None)
        if exception == self.sn:
            return " "
        return template.compile(self)    
    
    @property
    def peer_desc(self, peer):
        return "TO-{0}".format(peer.hostname)
        
    @property    
    def mlag_address(self):
        try:
            neighbor = DEVICES[HOST_TO_SN[self.mlag_neighbor]]
            mgmt_ip = ip_address(unicode(self.mgmt_ip))
            neighbor_mgmt = ip_address(unicode(neighbor.mgmt_ip))
            global_mlag_address = ip_address(unicode(searchConfig('mlag_address')))
            if mgmt_ip > neighbor_mgmt:
                return global_mlag_address + 1
            else:
                return global_mlag_address
        except:
            return ' '
        
    @property
    def mlag_peer_address(self):
        try:
            neighbor = DEVICES[HOST_TO_SN[self.mlag_neighbor]]
            return str(neighbor.mlag_address)
        except:
            return ' '
    
    @property
    def reload_delay_0(self):
        if getattr(self, "is_jericho", None):
            return searchConfig('reload_delay_jericho')[0]
        else:
            return searchConfig('reload_delay')[0]
        
    @property
    def reload_delay_1(self):
        if getattr(self, "is_jericho", None):
            return searchConfig('reload_delay_jericho')[1]
        else:
            return searchConfig('reload_delay')[1]
    
    @property
    def underlay_bgp(self):
        
        template = TEMPLATES.get('underlay_bgp')
        i = 0
        
        if len(self.underlay_inject):
            return "\n".join(self.underlay_inject)
        
        for i, spine in enumerate(SPINES, start = 1):
            #compile p2p link to spine
            
            try:
                ipAddress = ip_address(unicode(getattr(self, "sp{0}_ip".format(i))))
                spine_args = {
                    "interface" : getattr(self, "sp{0}_int".format(i)),
                    "address" : ipAddress,
                    "interface_speed" : getattr(self, "sp{0}_speed".format(i), searchConfig('fabric_speed')),
                    "description" : "TO-{0}-FABRIC".format(self.hostname)
                }
                spine.underlay_inject.append(template.compile(spine_args))
                self_args = {
                    "interface" : getattr(self, "lf{0}_int".format(i)),
                    "address" : ipAddress + 1,
                    "interface_speed" : getattr(self, "sp{0}_speed".format(i), searchConfig('fabric_speed')),
                    "description" : "TO-{0}-FABRIC".format(spine.hostname)
                }
                self.underlay_inject.append(template.compile(self_args))
                
            except Exception as e:
                LOGGER.log("Error building configlet underlay for {0}<->{1}: {2}".format(spine.hostname, self.hostname, e))
                sys.exit(0)
            
        return "\n".join(self.underlay_inject)
    
    @property
    def vrf_definition_bgp(self):
        template = TEMPLATES.get('vrf_definition_bgp')
        return self.compile_configlet(template)

    @property
    def spine_asn(self):
        if len(SPINES) >= 1:
            return SPINES[0].asn
        else:
            return None
        
    @property
    def spine_peer_filter(self):
        if self.role == 'spine':
            if ASN_RANGE.find(',') == -1:
                asn_range = "10 match as-range {0} result accept".format(ASN_RANGE)
            else:
                priority = 10
                asn_range = ""
                for _asn in ASN_RANGE.split(','):
                    asn_range = asn_range + "\t{0} match as-range {1} result accept\n".format(priority, _asn)
                    priority += 10
          
        
class Manager():
    
    def __init__(self):
        global DEVICES
        global SPINES
        global HOST_TO_SN
        self.tasks_to_deploy = []
        with open("fabric_parameters.csv") as f:
            reader = csv.reader(f)
            headers = [header.lower() for header in next(reader)]
            #row[0] is the serial
            #passing a dict to the switch to preserve csv headers
            for row in reader:
                sn = row[0]
                role_index = headers.index("role")
                
                DEVICES[sn] = Switch(dict(zip(headers,row)), CVP.getBySerial(sn))
                HOST_TO_SN[DEVICES[sn].hostname] = sn
                if row[role_index].lower() == "spine": #and (searchConfig('spines'] and searchConfig('spines'].index(sn)):
                    SPINES.append(DEVICES[sn])
    
    def deploy(self, recipe):
        for sn, device in DEVICES.items():
            for configlet in recipe:
                configlet = TEMPLATES[configlet]
                device.assign_configlet(configlet)
            if device.role == "spine":
                self.tasks_to_deploy.append(Task(device))
            else:
                self.tasks_to_deploy.insert(0,Task(device))
                
        for task in self.tasks_to_deploy:
            task.execute()
        self.tasks_to_deploy = []
            
                
#HELPER FN FOR DEALING WITH OPTIONS IN BASE CONFIGLET TEMPLATES                    
#used to fetch all the required variables defined in related_templates
#from either a device or global config
#logs error for specific failed value and current option


#get if dict, getattr if else
def searchSource(key, source):
    return source.get(key, None) if type(source) is dict else getattr(source, key, None)

def searchConfig(key, section = None):
    config = None
    if section:
        try:
            config = CONFIG.get(section, key)
        except:
            pass
    if not config:
        try:
            config = CONFIG.get('global', key)
        except:
            return None

    if config.startswith('[') and config.endswith(']'):
        config = [v.strip() for v in config[1:-1].split('|')]
    return config

def getKeyDefinition(key, source, section = None):
    return searchSource(key, source) or searchConfig(key, section)

def parseForRequiredKeys(template):
    return re.findall('{(.*?)}', template)

def parseForIterables(template):
    return re.findall('\[[\s\S]*?\](?!else)', template)

def parseForSections(template):
    return re.findall('(@[\s\S]*?@)({.*?})*', template)

#this should never fail
def parseSectionDefinition(template):
    return re.findall('(?<=@)[\s\S]*?(?=@))', template)[0]

def parseCondition(keys):
    condition_list = []
    _keys = keys.split('|')
    for key in _keys:
        key = re.split('([^a-z0-9A-Z_]+)', key)
        if len(key) > 1:
            condition = key[1]
            if condition == '=':
                condition_fn = lambda key, value, source = None, section = None : value == getKeyDefinition(key, source, section)
            else:
                condition_fn = lambda key, value, source = None, section = None : value != getKeyDefinition(key, source, section)
            condition_list.append( ((key[0], key[2]), condition_fn) )
        else:
            condition_list.append( ((key[0],), lambda key, source = None, section = None : bool(getKeyDefinition(key, source, section))) )
    return condition_list

def buildValueDict(source, template, injectSection = None):
    valueDict = {}
    valueDict['error'] = []
    
    neededKeys = parseForRequiredKeys(template)
    
    for key in neededKeys:
        #check if dict already has defined
        if valueDict.get(key, None):
            continue
        
        defined = getKeyDefinition(key, source, injectSection)
        if not defined:
            valueDict['error'].append(key)
        else:
            valueDict[key] = defined
        
    return valueDict

def getBySerial(sn):
    return DEVICES[sn]

class Configlet():
    def __init__(self, name, params = {}, injectSection = None):        
        self.name = name
        self.injectSection = injectSection
        for k, v in params.items():
            setattr(self, k, v)  
              
    
        
    def compileIterables(self, source, baseTemplate):
        compiled = {}
        compiled['error'] = []
        iterables = parseForIterables(baseTemplate)
        for template in iterables:
            extractedTemplates = [v.strip('[]') for v in template.split('else')]
            for i, _template in enumerate(extractedTemplates):
                valueDict = buildValueDict(source, _template, self.injectSection)
                errorKeys = valueDict.pop('error')
                if not errorKeys:
                    #values is a dict
                    keys = valueDict.keys()
                    values_list = valueDict.values()
                    
                    #basically turn lists into iterables and static values into functions which return the same thing everytime
                    #this way we can exhause iterators until they fail as we build new dicts to pass as single values
                    #if the flag is never set i.e. no lists are found just return one
                    values_and_getters = []
                    _compiled = []
                    flag = False
                    for item in values_list:
                        if type(item) == list:
                            #found at least one list
                            flag = not flag if not flag else flag
                            #i = element in lists to iterate
                            values_and_getters.append((iter(item),lambda item:next(item)))
                        else:
                            values_and_getters.append((item, lambda item:item))
                    #exhaust iterators
                    try:
                        while flag:
                            _compiled.append(_template.format(**dict(zip(keys, [function(value) for value, function in values_and_getters]))))
                            
                    except StopIteration:
                        compiled[template] = '\n'.join(_compiled)
                    #no lists were found return once
                    compiled[template] =  _template.format(**dict(zip(keys, [function(value) for value, function in values_and_getters])))
                    if i == 0:
                        break
                    if i == 1:
                        compiled['error'].pop()
                        
                else:
                    compiled['error'].append((template, errorKeys))
        return compiled
    #source can be either dict or object class i.e. getattr(CLASS, VALUE, None) or DICT.get(value,None)
    #will be used accordingly
    
    
    def compile(self, source):
        baseTemplate = self.basetemplate
        
        #parse for sections @...@{test}
        #and recurse on stripped sections
        sections = parseForSections(baseTemplate)
        for section in sections:
            #has clause to enable/disable
            _section, _test = section
            __section = _section.strip('@')
            compiledIterables = self.compileIterables(source, __section)
            errorIterables = compiledIterables.pop('error')
            #test the "tests" arguments i.e @...@{tests}
            failedTests = [v[0] for v, fn in parseCondition(_test.strip('{}')) if not fn(*v, source = source, section = self.injectSection)]
            
            if _test and not (failedTests or errorIterables):
                #there is a test and all passed COMPILE
                for toReplace, compiled in compiledIterables.items():
                    __section = __section.replace(toReplace, compiled)           
            elif _test and failedTests:
                #there is a test but failed WIPE
                LOGGER.log("Error building configlet section {0} in {1}: test condition for {2} failed ".format(
                    _section.replace('\n','')[:15],
                    self.name,
                    ','.join(failedTests)
                ))
                __section = ''
            elif compiledIterables and not errorIterables:
                #there is no test, decide with iterables
                for toReplace, compiled in compiledIterables.items():
                    __section = __section.replace(toReplace, compiled)  
            else:
                for toReplace, errorKeys in errorIterables:
                    LOGGER.log("Error building configlet section {0} in {1}: iterations failed on {2}".format(
                        _section.replace('\n','')[:15],
                        self.name,
                        ','.join(errorKeys)
                    ))
                __section = ''
            baseTemplate = baseTemplate.replace(_section + _test, '')
            
        #parse stuff in [] for iterations outside of sections
        #support only one iterable for now from the global space
        compiledIterables = self.compileIterables(source, baseTemplate)
        errorIterables = compiledIterables.pop('error')
        for toReplace, compiled in compiledIterables.items():   
            baseTemplate = baseTemplate.replace(toReplace, compiled)  
        for toReplace, errorKeys in errorIterables:
            baseTemplate = baseTemplate.replace(toReplace, '')
            
        #now deal with the base template after sections/iterables are worked out
        valueDict = buildValueDict(source, baseTemplate, injectSection = self.injectSection)
        errorKeys = valueDict.pop('error')
        try:
            baseTemplate = baseTemplate.format(**valueDict)
        except KeyError as E:
            LOGGER.log("Error building configlet {0}: global/device definition for {1} undefined".format(self.name, E))
            #must return a value which passes a boolean test
            #we will usually get here if the parent configlet requires device @property functions but the 
            return ' '

        return baseTemplate.replace("~","\t").strip()

def parseAgain(injectSection):
    global TEMPLATES
    global CONFIG
    
    #INIT CONFIG
    CONFIG = SafeConfigParser()
    CONFIG.read('fabric_builder_global.conf')
    
    #INIT TEMPLATES
    parser = SafeConfigParser()
    parser.read('fabric_builder_templates.conf')
    for sectionName in parser.sections():
        TEMPLATES[sectionName] = Configlet(sectionName, dict(parser.items(sectionName)), injectSection)
       
class FabricBuilder(cmd.Cmd):
    """Arista Fabric Initializer"""
    

            
    def do_deploy(self, section):
        parseAgain(section)
        recipe = searchConfig("recipe", section)
        MANAGER.deploy(recipe)
        
    def do_test(self, line):
        parseAgain()
        sn, name = line.split(',')
        getBySerial(sn).compile_configlet(TEMPLATES[name])
        
    def do_teapi(self,ip):
        #PYEAPI
        #conn = pyeapi.connect(host=ip,username=searchConfig('cvp_user'],password=searchConfig('cvp_pass'])
        #print conn.execute(["show platform"])
        
        switch = Server( "https://{0}:{1}@10.20.30.23/command-api".format(searchConfig('cvp_user'),searchConfig('cvp_pass')) )
        response = switch.runCmds( 1, [ "show platform jericho" ], 'text' ) 
        print response
        
    def do_EOF(self, line):
        return True
    
def main():
    global TEMPLATES
    global CONFIG
    global CVP 
    global MANAGER 
    
    #INIT CONFIG
    CONFIG = SafeConfigParser()
    CONFIG.read('fabric_builder_global.conf')
    
    #INIT LOGGER
    global LOGGER
    LOGGER = Log()
    
    #INIT TEMPLATES
    parser = SafeConfigParser()
    parser.read('fabric_builder_templates.conf')
    for section in parser.sections():
        TEMPLATES[section] = Configlet(section, dict(parser.items(section)))
        
    #INIT CVP
    CVP = Cvp()
    
    #INIT MANAGER
    MANAGER = Manager()

    FabricBuilder().cmdloop()



if __name__ == '__main__':
    main()
        
        

