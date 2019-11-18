import cmd
import csv
from ConfigParser import SafeConfigParser
from collections import defaultdict
import urllib3
import re
from ipaddress import ip_address
import os, ssl
import sys
import datetime
from itertools import chain

LOGGER = None
CVP = None
CONFIG = {}
TEMPLATES = {}
DEVICES = {}
HOST_TO_DEVICE = {}
SUPPLEMENT_FILES = {}
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

        self.cvprac = None
        self.containerTree = {}
        self.CvpApiError = None
        self.devices = {}
        self.host_to_device = {}           
        try:
            from cvprac.cvp_client import CvpClient
            from cvprac.cvp_client_errors import CvpApiError
            self.CvpApiError = CvpApiError
            self.cvprac = CvpClient()
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # to supress the warnings for https
            self.cvprac.connect([searchConfig('cvp_server')], searchConfig('cvp_user'), searchConfig('cvp_pass'))
            LOGGER.log("Successfully authenticated to CVP")
        except ImportError:
            LOGGER.log("Unable to find the CVPRAC module")
            
        
        #try:
        self.containers = self.cvprac.api.get_containers()['data']
        for cont in self.containers:
            self.containerTree[cont['name'].lower()] = [_cont['name'].lower() for _cont in self.containers if _cont['parentName'] == cont['name']]
        for device in self.cvprac.api.get_inventory():
            self.devices[device['serialNumber'].lower()] = device
            self.host_to_device[device['hostname'].lower()] = self.devices[device['serialNumber'].lower()]
            
        #except:
        #    LOGGER.log("Unable to connect to CVP Server")
        #    sys.exit(0)
    
    def getBySerial(self, sn):
        return self.devices.get(sn.lower(), None)
    
    def getByHostname(self, hostname):
        return self.host_to_device.get(hostname.lower(), None)
    
    def getContainerDevices(self, containerName, follow = False):
        tree = [containerName] + self.containerTree[containerName] if follow else [containerName]
        return [device for device in self.devices.values() if device['containerName'].lower() in tree]
    
    #returns key if successful
    def addOrUpdateConfiglet(self, configlet_name, configlet_content):
        # Check if we already have a configlet by this name
        if self.cvprac:
            try:
                configlet = self.cvprac.api.get_configlet_by_name(configlet_name)
            except self.CvpApiError as err:
                if 'Entity does not exist' in err.msg:
                    # Configlet doesn't exist let's create one
                    result = self.cvprac.api.add_configlet(configlet_name, configlet_content)
                else:
                    raise
            else:
                # Configlet does exist, let's update the content only if not the same (avoid empty task)
                if configlet['config'] != configlet_content:
                    result = self.cvprac.api.update_configlet(configlet_content, configlet['key'], configlet_name)
            
            return self.cvprac.api.get_configlet_by_name(configlet_name)['key']
        else:
            return None
    
    def deployDevice(self, device, container, configlets_to_deploy):
        if self.cvprac:
            try:
                if device.cvp['provisioned']:
                    ids = self.cvprac.api.apply_configlets_to_device('fabric_builder', device, configlets_to_deploy)
                else:
                    
                    ids = self.cvprac.api.deploy_device(device, container, configlets_to_deploy)
                print ids
            except self.CvpApiError as err:
                LOGGER.log("Deploying device {0}: failed, could not get task id from CVP".format(device.sn))
            else:
                LOGGER.log("Deploying device {0}: {1} to {2} container with task id {3}".format(device.sn, device.mgmt_ip, device.container, ids))
        else:
            return None
            
    def getTelemetry(self, sn, query):
        query = '/api/v1/rest/{0}{1}'.format(sn, query)
        return self.cvprac.get(query)
        
    def parseTelemetry(self, response, key):
        pass
        
class Task():
    def __init__(self, device = None, template = None, apply_to = None):
        self.device = device
        self.template = template
        self.apply_to = apply_to
    #the task finally figures out what to assign and compile
    def execute(self):
        configlet_keys = []
        if not self.template:
            for item in self.device.to_deploy:
                name, configlet = item
                if searchConfig('debug'):
                    print '*'*50
                    print name
                    print '*'*50
                    print configlet.compile(self.device)
                    print '*'*50
                else:
                    #configlet_keys.append(CVP.addOrUpdateConfiglet(name, configlet.compile(self.device)))
                    #tasks = CVP.deployDevice(self.device.cvp, self.device.container, configlet_keys)
                    print "I am where I want to be"
            self.device.to_deploy = []
        else:
            #deal with singletons
            print "Singleton, Whoo Hoo! Far Boo"
            print self.template.compile({})
            print self.apply_to
                
        
            

class Switch():
    
    def __init__(self, params={}, cvpDevice=None, injectSection = None, implicitRole = None):
        #list to hold leaf compiled spine underlay interface init
        self.underlay_inject = []
        self.to_deploy = []
        self.injectSection = injectSection
        self.cvp = None
        for k, v in params.items():
            setattr(self, k, str(v).replace("|",","))
            
        self.sn = (getattr(self, 'serialNumber') or getattr(self, 'sn')).lower()
        
        if implicitRole == 'spine':
            self.role = 'spine'
        elif params is cvpDevice:
            self.role = 'cvp_device'
        
        if cvpDevice:
            self.cvp = cvpDevice
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, 'x'))
        else:
            LOGGER.log("Device init {0}, Role: {1}, CVP found: ({2})".format(self.sn, self.role, ''))
    
    def searchConfig(self, key):
        return searchConfig(key, self.injectSection)
            
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
            return ' '
        exception = getattr(template, "skip_device", None)
        if exception == self.sn:
            return ' '
        return template.compile(self)    
    
    @property
    def peer_desc(self, peer):
        return "TO-{0}".format(peer.hostname)
        
    @property    
    def mlag_address(self):
        try:
            neighbor = HOST_TO_DEVICE[self.mlag_neighbor]
            mgmt_ip = ip_address(unicode(self.mgmt_ip))
            neighbor_mgmt = ip_address(unicode(neighbor.mgmt_ip))
            global_mlag_address = ip_address(unicode(self.searchConfig('mlag_address')))
            if mgmt_ip > neighbor_mgmt:
                return global_mlag_address + 1
            else:
                return global_mlag_address
        except:
            return ' '
        
    @property
    def mlag_peer_address(self):
        try:
            neighbor = HOST_TO_DEVICE[self.mlag_neighbor]
            return str(neighbor.mlag_address)
        except:
            return ' '
    
    @property
    def reload_delay_0(self):
        if getattr(self, "is_jericho", None):
            return self.searchConfig('reload_delay_jericho')[0]
        else:
            return self.searchConfig('reload_delay')[0]
        
    @property
    def reload_delay_1(self):
        if getattr(self, "is_jericho", None):
            return self.searchConfig('reload_delay_jericho')[1]
        else:
            return self.searchConfig('reload_delay')[1]
    
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
                    "interface_speed" : getattr(self, "sp{0}_speed".format(i), self.searchConfig('fabric_speed')),
                    "description" : "TO-{0}-UNDERLAY".format(self.hostname)
                }
                spine.underlay_inject.append(template.compile(spine_args))
                self_args = {
                    "interface" : getattr(self, "lf{0}_int".format(i)),
                    "address" : ipAddress + 1,
                    "interface_speed" : getattr(self, "sp{0}_speed".format(i), self.searchConfig('fabric_speed')),
                    "description" : "TO-{0}-UNDERLAY".format(spine.hostname)
                }
                self.underlay_inject.append(template.compile(self_args))
                
            except Exception as e:
                LOGGER.log("Error building configlet section underlay for {0}<->{1}: {2}".format(spine.hostname, self.hostname, e))
                sys.exit(0)
            
        return "\n".join(self.underlay_inject)

    @property
    def spine_asn(self):
        if len(SPINES) >= 1:
            return SPINES[0].asn
        else:
            return None

          
    @property
    def spine_lo0_list(self):
        return [spine.lo0 for spine in SPINES]
    
    @property
    def spine_ipv4_list(self):
        ipAddresses = []
        for i, spine in enumerate(SPINES, start = 1):
            #compile p2p link to spine
            ipAddresses.append(getattr(self, "sp{0}_ip".format(i)))
        return ipAddresses
    
    @property
    def spine_hostname_list(self):
        return [spine.hostname for spine in SPINES]
    
    @property
    def ibgp_peer_address(self):
        return ip_address(unicode(self.searchConfig('ibgp_ip'))) + 1
    
def fetchDevices(search, follow_child_containers = False):
    search = search if type(search) == list else [search]
    devices = []
    for _search in search:
        _search = _search.lower()
        try:
            device = CVP.getBySerial(_search) or CVP.getByHostname(_search)
            if device:
                devices.append((device,))
                continue
            else:
                devices.append(CVP.getContainerDevices(_search, follow_child_containers))
        except KeyError as E:
            LOGGER.log("Could not find {0}".format(_search))
    return list(chain.from_iterable(devices))   
    
        
class Manager():
    
    def __init__(self):
        self.tasks_to_deploy = []    
        
    def deploy(self, section):
        
        recipe = searchConfig("recipe", section)
        mode = searchConfig('mode', section)
        
        #control what tasks get created, DEVICES are already loaded accordingly
        if mode == 'day1':
            for sn, device in DEVICES.items():
                
                for template in recipe:
                    template = TEMPLATES[template]
                    device.assign_configlet(template)
                if device.role == "spine":
                    self.tasks_to_deploy.append(Task(device))
                else:
                    self.tasks_to_deploy.insert(0,Task(device))
                    
            
        elif mode == 'day2':
            singleton = searchConfig('singleton', section)
            if singleton:
                apply_to = searchConfig('apply_to', section)
                for template in recipe:
                    template = TEMPLATES[template]
                    self.tasks_to_deploy.append(Task(template = template, apply_to = apply_to))
            else:
                print DEVICES
                for sn, device in DEVICES.items():
                
                    for template in recipe:
                        template = TEMPLATES[template]
                        device.assign_configlet(template)
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
def searchSource(key, source, default = None):
    return source.get(key, default) if type(source) is dict else getattr(source, key, default)

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
        return [v.strip() for v in config[1:-1].split('|')]
        
    if config == 'True':
        return True
    if config == 'False':
        return False
    
    return config

def getKeyDefinition(key, source, section = None):
    
    csv_telemetry_source = key.split('#')
    found = None
    math = re.findall('(\w+)([+\-*]+)(\d+)?', key)   
    
    if len(csv_telemetry_source) == 2:
        file = csv_telemetry_source[0]
        _key = csv_telemetry_source[1]
        math = re.findall('(\w+)([+\-*]+)(\d+)?', _key)
        _key = math[0][0] if math else _key
        if file.startswith('/') and hasattr(CVP, 'cvprac'):
            found = CVP.cvprac.get('/api/v1/rest/' + searchSource('sn', source, '').upper() + file)
            try:
                found = found['notifications'][0]['updates'][_key]['value']
                __keys = found.keys()
                if 'Value' in __keys:
                    found = found['Value']
                elif 'value' in __keys:
                    found = found['value']
                _type, val = found.items()[0]
                found = val
            except:
                pass
        else:
            global SUPPLEMENT_FILES
            try:
                found = SUPPLEMENT_FILES[file][_key]
            except KeyError:
                with open(file+'.csv') as f:
                    
                    SUPPLEMENT_FILES[file] = defaultdict(list)
                    reader = csv.DictReader(f)
                    for row in reader:
                        for k, v in row.items():
                            SUPPLEMENT_FILES[file][k].append(v)
                found = SUPPLEMENT_FILES[file][_key]
            
         
    key, op, qty = (found or math[0][0],) + math[0][1:] if math else (found or key, None, None)
    
    if op:
        if type(key) == list:
            return (key, op, qty)
        elif key.isdigit():
            return (int(key), op, qty)
        else:
            return (int(searchSource(key, source) or searchConfig(key, section)), op, qty)
        
        

    return found or searchSource(key, source) or searchConfig(key, section)

def parseForRequiredKeys(template):
    return re.findall('{(.*?)}', template)

def parseForIterables(template):
    return re.findall('\[[\s\S]*?\](?!else)', template)

def parseForSections(template):
    return re.findall('(@[\s\S]*?@)({.*?})*', template)

#builds a tuple of values followed by a comparator lambda
#used to check if tests pass while supporting section injections from the global variable space

def buildConditionTest(keys):
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
    
    keys = parseForRequiredKeys(template)
    
    for key in keys:
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
    return DEVICES[sn.lower()]

class Math():
    def __init__(self, start, op, qty):
        
        self.iter = None
        self.counter = None
        
        
        if type(start) == list:
            self.iter = iter(start)
        else:  
            self.counter = int(start)

        
        if op == '+':
            self.do = self.increment
            self.qty = int(qty) if qty else 1
        elif op == '++':
            self.do = self.increment
            self.qty = int(qty) if qty else 10
        elif op == '*':
            self.do = self.multiply
            self.qty = int(qty) if qty else 1
    
    def current(self):
        return int(next(self.iter)) if self.iter else self.counter
    
    def store(self):
        if self.counter:
            self.counter += self.qty
    
    def increment(self):
        current = self.current()
        self.store()
        return current
    
    def multiply(self):
        current = self.current()
        return current * self.qty
        
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
                    #this way we can exhause iterators until they fail as we build new dicts to pass as args
                    #if the flag is never set i.e. no lists are found just return one
                    values_and_getters = []
                    _compiled = []
                    flag = False
                    for item in values_list: 
                        if type(item) == list:
                            #found at least one list
                            flag = not flag if not flag else flag
                            values_and_getters.append((iter(item), lambda item:next(item)))
                        elif type(item) == tuple:
                            values_and_getters.append((Math(*item), lambda item:item.do()))
                        else:
                            values_and_getters.append((item, lambda item:item))
                    #exhaust iterators
                    try:
                        while flag:

                            _compiled.append(_template.format(**dict(zip(keys, [function(value) for value, function in values_and_getters]))))
                        else:
                            #no lists were found return once
                            compiled[template] = _template.format(**dict(zip(keys, [function(value) for value, function in values_and_getters])))    
                    except StopIteration:
                        compiled[template] = '\n'.join(_compiled)
                    
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
            #parseCondition returns a (value, function) tuple the fn(value) will return true/false if the test passes
            #here we collect the key which failed a test
            failedTests = [v[0] for v, fn in buildConditionTest(_test.strip('{}')) if not fn(*v, source = source, section = self.injectSection)]
            
            if _test and not (failedTests or errorIterables):
                #there is a test and iterables with no errors -> COMPILE
                for toReplace, compiled in compiledIterables.items():
                    __section = __section.replace(toReplace, compiled)        
            elif _test and failedTests:
                #there is a test but failed WIPE
                LOGGER.log("Error building configlet section {0} in {1}: test condition for {2} failed".format(
                    _section.replace('\n','')[:15],
                    self.name,
                    ','.join(failedTests)
                ))
                __section = ''
            elif compiledIterables and not errorIterables:
                #there is no test, and all iterables passed COMPILE
                for toReplace, compiled in compiledIterables.items():
                    __section = __section.replace(toReplace, compiled) 
            else:
                #no test, iterables failed WIPE
                for toReplace, errorKeys in errorIterables:
                    LOGGER.log("Error building configlet section {0} in {1}: iterations failed on {2}".format(
                        _section.replace('\n','')[:15],
                        self.name,
                        ','.join(errorKeys)
                    ))
                __section = ''
            baseTemplate = baseTemplate.replace(_section + _test, __section)

        #parse stuff in [] for iterations outside of sections
        #support only one iterable for now from the global space
        compiledIterables = self.compileIterables(source, baseTemplate)
        errorIterables = compiledIterables.pop('error')
        
        for toReplace, compiled in compiledIterables.items():   
            baseTemplate = baseTemplate.replace(toReplace, compiled)  
            
        for toReplace, errorKeys in errorIterables:
            baseTemplate = baseTemplate.replace(toReplace, '')
            
        #now deal with the base template after sections/iterables are worked out
        valueDict = buildValueDict(source, baseTemplate, self.injectSection)
        errorKeys = valueDict.pop('error')
        if errorKeys:
            LOGGER.log("Error building configlet {0}: global/device definition for {1} undefined".format(self.name, ','.join(errorKeys)))
            return ' '
        try:
            baseTemplate = baseTemplate.format(**valueDict)
        except KeyError as E:
            LOGGER.log("Error building configlet {0}: global/device definition for {1} undefined".format(self.name, E))
            #must return a value which passes a boolean test
            #we will usually get here if the parent configlet requires device @property functions but the 
            return ' '

        return baseTemplate.replace("~","\t").strip()

def buildGlobalData(injectSection = None):
    #INIT CONFIG
    loadConfig()
    #INIT TEMPLATES
    loadTemplates(injectSection)
    #INIT FABRIC CSV
    loadDevices(injectSection)
      
def loadConfig():
    global CONFIG
    CONFIG = {} 
    CONFIG = SafeConfigParser()
    CONFIG.read('global.conf')
    
def loadTemplates(injectSection = None):
    global TEMPLATES
    TEMPLATES = {}
    parser = SafeConfigParser()
    parser.read('templates.conf')
    for sectionName in parser.sections():
        TEMPLATES[sectionName] = Configlet(sectionName, dict(parser.items(sectionName)), injectSection)
    
def loadDevices(injectSection = None):
    global DEVICES
    global SPINES
    global HOST_TO_DEVICE

    
    DEVICES = {}
    SPINES = []
    HOST_TO_DEVICE = {}
    
    mode = searchConfig('mode', injectSection)
    
    def appendDevice(device, to, implicitRole = False):
        sn = device['serialNumber'].lower()
        to[sn] = Switch(device, device, injectSection, implicitRole)
        HOST_TO_DEVICE[to[sn].hostname.lower()] = to[sn]

    if mode == 'day2':
        spines = searchConfig('spines', injectSection)
        follow_child_containers = searchConfig('follow_child_containers', injectSection)
        spines = fetchDevices(spines, follow_child_containers)
        devices = fetchDevices(searchConfig('compile_for', injectSection), follow_child_containers)
        for device in devices:
            appendDevice(device, DEVICES)
        for device in spines:
            sn = device['serialNumber'].lower()
            SPINES.append(Switch(device, device, injectSection, implicitRole = 'spine'))
            
    elif mode == 'day1':
        with open("fabric_parameters.csv") as f:
            reader = csv.reader(f)
            headers = [header.lower() for header in next(reader)]
            #row[0] is the serial
            #passing a dict to the switch to preserve csv headers
            for row in reader:
                sn = row[0].lower()
                role_index = headers.index("role")
                
                DEVICES[sn] = Switch(dict(zip(headers,row)), CVP.getBySerial(sn), injectSection)
                HOST_TO_DEVICE[DEVICES[sn].hostname.lower()] = DEVICES[sn]
                if row[role_index].lower() == "spine":
                    SPINES.append(DEVICES[sn])
    
    
    
class FabricBuilder(cmd.Cmd):
    """Arista Fabric Initializer"""
    intro = 'Type ? for available commands' 
    prompt = 'builder>'
    
    def help_deploy(self):
        print 'Use deploy NAME where NAME is the user-defined section with a defined recipe.'
    
    #check recipe syntax and variables
    def do_deploy(self, section):
        mode = searchConfig('mode', section)
        if mode == 'day2':
            follow_child_containers = searchConfig('follow_child_containers', section)
            spines = searchConfig('spines', section)
            leafs = searchConfig('leafs', section)
            if not (spines and leafs):
                LOGGER.log('Recipe error: for mode = day2, spines and leaves must be defined in the global or recipe config')
                return True
            singleton = searchConfig('singleton', section)
            compile_for = searchConfig('compile_for', section)
            if not singleton and not compile_for:
                LOGGER.log('Recipe error: for singleton = False, compile_for must be defined in the global or recipe config')
                return True

        buildGlobalData(section)
        MANAGER.deploy(section)
        
        
    def do_test(self, line):
        args = line.split(',')
        buildGlobalData(args[2] if 2 < len(args) else None)
        getBySerial(args[0]).compile_configlet(TEMPLATES[args[1]])
        
    def do_compile(self, line):
        args = line.split(',')
        
    def do_teapi(self,ip):
        #PYEAPI
        #conn = pyeapi.connect(host=ip,username=searchConfig('cvp_user'],password=searchConfig('cvp_pass'])
        #print conn.execute(["show platform"])
        
        switch = Server( "https://{0}:{1}@10.20.30.23/command-api".format(searchConfig('cvp_user'),searchConfig('cvp_pass')) )
        response = switch.runCmds( 1, [ "show platform jericho" ], 'text' ) 
        print response
        
    def do_EOF(self, line):
        return True
    
def debug():
    #INIT CONFIG
    loadConfig()

    #INIT LOGGER
    global LOGGER
    LOGGER = Log()
        
    #INIT CVP
    global CVP
    CVP = Cvp()
    
    #INIT MANAGER
    global MANAGER 
    MANAGER = Manager()
    
def main():
    debug()

    FabricBuilder().cmdloop()



if __name__ == '__main__':
    main()
        
        
