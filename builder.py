import cmd
import csv
from backports.configparser import ConfigParser
import urllib3
import re
from ipaddress import ip_address
import os, ssl
import sys
import datetime
import xlrd
from itertools import chain

LOGGER = None
CVP = None
CONFIG = {}
TEMPLATES = {}
DEVICES = {}
COMPILE_FOR = []
ASSIGN_TO = []
HOST_TO_DEVICE = {}
SUPPLEMENT_FILES = {}
SPINES = []
DEBUG = False

class Log():
    def __init__(self):
        self.fabric_builder_log = open('fabric_builder_log.txt', 'a')
        
    def log(self,string):
        string = "{0}: {1}\n".format( datetime.datetime.now().strftime('%a %b %d %H:%M'), string )
        sys.stderr.write(string)
        self.fabric_builder_log.write(string)
  
class Cvp():
    def __init__(self):

        self.cvprac = None
        self.containerTree = {}
        self.CvpApiError = None
        self.devices = {}
        self.host_to_device = {}
        self.containers = {}
        self.configlets = {}
        
        try:
            from cvprac.cvp_client import CvpClient
            from cvprac.cvp_client_errors import CvpClientError
            from cvprac.cvp_client_errors import CvpApiError
            self.CvpClientError = CvpClientError
            self.CvpApiError = CvpApiError
            self.cvprac = CvpClient()
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # to supress the warnings for https
            self.cvprac.connect([searchConfig('cvp_server')], searchConfig('cvp_user'), searchConfig('cvp_pass'))
            LOGGER.log("Successfully authenticated to CVP")
        except (ImportError, self.CvpClientError) as e:
            LOGGER.log("Unable to Init CVP; forcing debug mode")
            LOGGER.log("ERROR: {0}".format(e))
            global DEBUG
            DEBUG = True
            
        
    def populate(self):
        
        try:
            LOGGER.log("-loading containers; please wait...")
            self.containers = {item['name'].lower():item for item in self.cvprac.api.get_containers()['data']}
            LOGGER.log("-loading configlets; please wait...")
            self.configlets = {item['name'].lower():item for item in self.cvprac.api.get_configlets()['data']}
            
            for name, cont in self.containers.items():
                self.containerTree[name] = [_name for _name, _cont in self.containers.items() if _cont['parentName'] == cont['name']]
                
            
            LOGGER.log("-loading devices; please wait...")
            for device in self.cvprac.api.get_inventory():
                sn = device['serialNumber'].lower()
                host = device['hostname'].lower()
                LOGGER.log("-loading {0} configlets; please wait...".format(host))
                configlets = self.cvprac.api.get_configlets_by_device_id(device['systemMacAddress'])
                device['configlets'] = {item['name'].lower():item for item in configlets}
                
                self.devices[sn] = device
                self.host_to_device[host] = self.devices[sn]
            
        except:
            LOGGER.log("Unable to connect to CVP Server")
            sys.exit(0)
    
    def getBySerial(self, sn):
        return self.devices.get(sn.lower(), None)
    
    def getByHostname(self, hostname):
        return self.host_to_device.get(hostname.lower(), None)
    
    def getContainerByName(self, name):
        return self.containers.get(name.lower(), None)
    
    def getContainerDevices(self, containerName, follow = False):
        containerName = containerName.lower()
        tree = [containerName] + self.containerTree[containerName] if follow else [containerName]
        return [device for device in self.devices.values() if device['containerName'].lower() in tree]
    
    def fetchDevices(self, search, follow_child_containers = False):
        search = search if type(search) == list else [search]
        devices = []
        for _search in search:
            
            try:
                device = CVP.getBySerial(_search) or CVP.getByHostname(_search)
                if device:
                    devices.append((device,))
                    continue
                else:
                    devices.append(CVP.getContainerDevices(_search, follow_child_containers))
            except KeyError as e:
                LOGGER.log("Could not find {0}".format(_search))
        return list(chain.from_iterable(devices))
    
    def createConfiglet(self, configlet_name, configlet_content):
        # Configlet doesn't exist let's create one
        LOGGER.log("--creating configlet {0}; please wait...".format(configlet_name))
        self.cvprac.api.add_configlet(configlet_name, configlet_content)
        return self.cvprac.api.get_configlet_by_name(configlet_name)
                
        
    def updateConfiglet(self, configlet, new_configlet_content):
        # Configlet does exist, let's update the content only if not the same (avoid empty task)
        configlet_name = configlet['name']
        LOGGER.log("--found configlet {0}".format(configlet_name))
        if configlet['config'] != new_configlet_content:
            LOGGER.log("---updating configlet {0}; please wait...".format(configlet_name))
            self.cvprac.api.update_configlet(new_configlet_content, configlet['key'], configlet_name)
        return self.cvprac.api.get_configlet_by_name(configlet_name)
                
    def deployDevice(self, device, container, configlets_to_deploy):
        try:
            ids = self.cvprac.api.deploy_device(device.cvp, container, configlets_to_deploy)
        except self.CvpApiError as e:
            LOGGER.log("---deploying device {0}: failed, could not get task id from CVP".format(device.hostname))
        else:
            ids = ','.join(map(str, ids['data']['taskIds']))
            LOGGER.log("---deploying device {0}: {1} to {2} container".format(device.hostname, device.mgmt_ip, device.container))
            LOGGER.log("---CREATED TASKS {0}".format(ids))
            
    def applyConfiglets(self, to, configlets):
        app_name = "CVP Configlet Builder"
        to = to if type(to) == list else [to]
        configlets = configlets if type(configlets) == list else [configlets]
        toContainer = None
        toDevice = None
        
        #dest is a container, sn. or hostname string
        for dest in to:
            
            toContainer = self.getContainerByName(dest)
            if toContainer:
                LOGGER.log("---applying configlets to {0}; please wait...".format(toContainer.name))
                _result = self.cvprac.api.apply_configlets_to_container(app_name, toContainer, configlets)
                dest = toContainer
            else:
                #apply to device
                toDevice = getBySerial(dest) or getByHostname(dest)
                dest = toDevice.hostname
                LOGGER.log("---applying configlets to {0}; please wait...".format(dest))
                _result = self.cvprac.api.apply_configlets_to_device(app_name, toDevice.cvp, configlets) if toDevice else None
            
            if not (toDevice or toContainer):
                errorOn = [_conf['name'] for _conf in configlets]
                LOGGER.log("---failed to push {0}; {1} not found".format(','.join(errorOn), dest))
            elif _result and _result['data']['status'] == 'success':
                
                LOGGER.log("---CREATED TASKS {0}".format(','.join(map(str, _result['data']['taskIds']))))
                
                
        return None    
    
        
class Task():
    def __init__(self, device = None, template = None, mode = None):
        self.device = device
        self.template = template
        self.singleton = True if template else False
        self.mode = mode
        
    #the task finally figures out what to assign and compile
    def execute(self):
        configlet_keys = []
        apply_configlets = searchConfig('apply_configlets')
        
        def pushToCvp():
            container = searchSource('container', self.device)
            
            if self.device.cvp['containerName'] == 'Undefined' and container:
                CVP.deployDevice(self.device, container, configlet_keys)
            elif self.device.cvp['containerName'] == 'Undefined' and not container:
                LOGGER.log("---cannot deploy {0}; non-provisioned device with no destination container defined".format(self.device.hostname))
            else:
                CVP.applyConfiglets(self.device.sn, configlet_keys) 
                
        if self.singleton:
            #deal with singletons
            name = "{0}-{1}".format(self.template.injectSection, self.template.name)
            name_lower = name.lower()
            LOGGER.log('COMPILING {0}'.format(name))
            new_configlet_content = self.template.compile({})
            assign_to = searchConfig('assign_to', self.template.injectSection)
            
            if not DEBUG:
                print('-'*50)
                LOGGER.log("EXECUTING TASKS FOR SINGLETON {0}".format(name))
                print('-'*50)
            else:
                print('-'*50)
                print('DEBUG SINGLETON OUTPUT: '+ name)
                print('-'*50)
                print("assign to: "+ ','.join(assign_to))
                print('-'*50)
                print(new_configlet_content)
                return
            
            exists = searchSource(name_lower, CVP.configlets, False)
                
            if not exists:
                configlet_keys.append(CVP.createConfiglet(name, new_configlet_content)) 
            else:
                CVP.updateConfiglet(exists, new_configlet_content)        
            
            if apply_configlets and assign_to and configlet_keys:
                createdTasks = CVP.applyConfiglets(assign_to, configlet_keys) if assign_to else []
                if createdTasks:
                    LOGGER.log("---successfully created tasks {0}".format(','.join(map(str, createdTasks))))

        #DAY1 and DAY2 EXECUTION HAPPENS HERE
        else:
            if not DEBUG:
                print('-'*50)
                LOGGER.log("EXECUTING TASKS FOR DEVICE {0}/{1}".format(self.device.hostname, self.device.sn))
                print('-'*50)
                
            configlet_keys = []
            
            for name, configlet in self.device.to_deploy:
                
                #IF DEBUG IS ON THEN JUST PRINT TO SCREEN
                if DEBUG:
                    print('-'*50)
                    print('DEBUG OUTPUT: '+ name)
                    print('-'*50)
                    print(configlet.compile(self.device))
                    continue
                
                #ELSE DOES IT EXIST AND ASSIGNED?
                name_lower = name.lower()
                
                exists = searchSource(name_lower, CVP.configlets, False)
                assigned = searchSource(name_lower, self.device.cvp['configlets'], False)
                
                LOGGER.log('COMPILING {0}'.format(name))
                new_configlet_content = configlet.compile(self.device)
                
                if not exists:
                    configlet_keys.append(CVP.createConfiglet(name, new_configlet_content)) 
                elif not assigned:
                    configlet_keys.append(CVP.updateConfiglet(exists, new_configlet_content))
                else:
                    CVP.updateConfiglet(exists, new_configlet_content)


            #DEVICES IN ASSIGN_TO ALWAYS FOLLOW CHILD CONTAINERS
            if not DEBUG and apply_configlets and configlet_keys:
                if self.mode == 2:
                    if ASSIGN_TO:
                        if self.device.cvp in ASSIGN_TO:
                            pushToCvp()
                    else:
                        pushToCvp()
                elif self.mode == 1:
                    pushToCvp()
            
            self.device.to_deploy = []
            
                

class Switch():
    
    def __init__(self, params={}, cvpDevice={}, injectSection = None, implicitRole = None):
        #list to hold leaf compiled spine underlay interface init
        self.underlay_inject = []
        self.to_deploy = []
        self.injectSection = injectSection
        self.cvp = None
        for k, v in params.items():
            setattr(self, k, str(v).replace("|",","))
        
        self.hostname = searchSource('hostname', self) or searchSource('hostname', cvpDevice)
        self.sn =       searchSource('sn', self) or searchSource('serialNumber', cvpDevice)
        
        if implicitRole:
            self.role = implicitRole
        elif not params and cvpDevice:
            self.role = 'cvp_device'
        
        if cvpDevice:
            self.cvp = cvpDevice
            LOGGER.log("Device init {0}, Role: {1}, Container: {2}, CVP found: ({3})".format(self.sn, self.role, self.cvp['containerName'], 'x'))
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
        configlet_name = "{0}-{1}-{2}-CONFIG".format(self.injectSection.upper(), template.name.upper(), self.hostname.upper())
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
            neighbor = getByHostname(self.mlag_neighbor)
            mgmt_ip = ip_address(unicode(self.mgmt_ip[:-3]))
            neighbor_mgmt = ip_address(unicode(neighbor.mgmt_ip[:-3]))
            global_mlag_address = ip_address(unicode(self.searchConfig('mlag_address')))
            if mgmt_ip > neighbor_mgmt:
                return global_mlag_address + 1
            else:
                return global_mlag_address
        except:
            return 'ERROR'
        
    @property
    def mlag_peer_address(self):
        try:
            neighbor = getByHostname(self.mlag_neighbor)
            return str(neighbor.mlag_address)
        except:
            return 'ERROR'
    
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
    def underlay(self):
        
        template = TEMPLATES.get('underlay_private')
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
                    "description" : "TO-{0}-UNDERLAY Ethernet{1}".format(self.hostname, getattr(self, "lf{0}_int".format(i)))
                }
                spine.underlay_inject.append(template.compile(spine_args))
                self_args = {
                    "interface" : getattr(self, "lf{0}_int".format(i)),
                    "address" : ipAddress + 1,
                    "interface_speed" : getattr(self, "sp{0}_speed".format(i), self.searchConfig('fabric_speed')),
                    "description" : "TO-{0}-UNDERLAY Ethernet{1}".format(spine.hostname, getattr(self, "sp{0}_int".format(i)))
                }
                self.underlay_inject.append(template.compile(self_args))
                
            except Exception as e:
                LOGGER.log("-error building configlet section underlay for {0}<->{1}: {2}".format(spine.hostname, self.hostname, e))
                sys.exit(0)
            
        return "\n".join(self.underlay_inject)

    @property
    def spine_asn(self):
        if len(SPINES) >= 1:
            return SPINES[0].asn
        else:
            return 'ERROR'

          
    @property
    def spine_lo0_list(self):
        return [spine.lo0 for spine in SPINES]
    
    @property
    def spine_lo1_list(self):
        return [spine.lo1 for spine in SPINES]
    
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
    def vrf_ibgp_peer_address(self):
        ip = self.searchConfig('vrf_ibgp_ip')
        return ip_address(unicode(ip)) + 1 if ip else 'ERROR'
    
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
    
    def increment(self):
        current = self.current()
        if self.iter:
            return current + self.qty
        else:
            self.counter += self.qty
            return current
    
    def multiply(self):
        current = self.current()
        if self.iter:
            return current * self.qty
        else:
            self.counter *= self.qty
            return current
        
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
                        #if the item is just a list without math then use StopIteration exception to stop iterations
                        if type(item) == list:
                            #found at least one list
                            flag = not flag if not flag else flag
                            values_and_getters.append((iter(item), lambda item:next(item)))
                        #if the item is a tuple then it wraps the item inside the tuple with math ops to be done e.g. (value, op, qty) where value can be a list, if so compile until exhausted
                        elif type(item) == tuple:
                            if type(item[0]) == list:
                                flag = not flag if not flag else flag
                            values_and_getters.append((Math(*item), lambda item:item.do()))
                        #this is a single value, no math, compile once
                        else:
                            values_and_getters.append((item, lambda item:item))
                    #sanitize format syntax from templates and replase actual keys with positionals        
                    _keys = []
                    
                    #don't modify existing i; this is to sanitize and replace invalid keys for the format function used later
                    for x, key in enumerate(keys, 0):
                        x = 'i'+str(x)
                        _template = _template.replace('{'+key+'}', '{'+x+'}')
                        _keys.append(x)
                        

                    #exhaust iterators
                    try:
                        #if flag is tripped then we know to iterate until the exception
                        while flag:

                            _compiled.append(_template.format(**dict(zip(_keys, [function(value) for value, function in values_and_getters]))))
                        else:
                            #no lists were found return once
                            compiled[template] = _template.format(**dict(zip(_keys, [function(value) for value, function in values_and_getters])))    
                    except StopIteration as e:
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
        #TODO: Right now all the string replacements happen literally carrying the groups as the toReplace parameters
        #can definitely do this better
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
                LOGGER.log("-skipping configlet section {0} in {1}: test condition for {2} failed".format(
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
                    LOGGER.log("-skipping configlet section {0} in {1}: iterations failed on {2}".format(
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
        for toReplace, errorKeys in errorIterables:
            LOGGER.log("-skipping configlet option {0} in {1}: variable {2} undefined".format(
                        toReplace.replace('\n','')[:15] + '...',
                        self.name,
                        ','.join(errorKeys)
            ))
        for toReplace, compiled in compiledIterables.items():   
            baseTemplate = baseTemplate.replace(toReplace, compiled)  
            
        for toReplace, errorKeys in errorIterables:
            baseTemplate = baseTemplate.replace(toReplace, '')
            
        #now deal with the base template after sections/iterables are worked out
        valueDict = buildValueDict(source, baseTemplate, self.injectSection)
        errorKeys = valueDict.pop('error')
        if errorKeys:
            LOGGER.log("-error building configlet {0}: global/device definition for {1} undefined".format(self.name, ','.join(errorKeys)))
            return ' '
        
        #this is to sanitize and replace invalid keys in the format function    
        _keys = []
        for i, key in enumerate(valueDict.keys(), 0):
            i = 'i'+str(i)
            baseTemplate = baseTemplate.replace('{'+key+'}', '{'+i+'}')
            _keys.append(i)
        try:
            baseTemplate = baseTemplate.format(**dict(zip(_keys, valueDict.values())))
        except KeyError as e:
            LOGGER.log("-error building configlet {0}: global/device definition for {1} undefined".format(self.name, e))
            #must return a value which passes a boolean test
            #we will usually get here if the parent configlet requires device @property functions but the 
            return ' '

        return baseTemplate.replace("~","\t").strip()   
  
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
                    self.tasks_to_deploy.append(Task(device, mode = 1))
                else:
                    self.tasks_to_deploy.insert(0,Task(device, mode = 1))
            
        elif mode == 'day2':
            singleton = searchConfig('singleton', section)
            
            if singleton:
                for template in recipe:
                    template = TEMPLATES[template]
                    self.tasks_to_deploy.append(Task(template = template, mode = 2))
            else:
                                
                for device in COMPILE_FOR:                
                    for template in recipe:
                        template = TEMPLATES[template]
                        device.assign_configlet(template)
                    if device.role == "spine":
                        self.tasks_to_deploy.append(Task(device, mode = 2))
                    else:
                        self.tasks_to_deploy.insert(0,Task(device, mode = 2))
            
        for task in self.tasks_to_deploy:
            task.execute()
        self.tasks_to_deploy = []

class FabricBuilder(cmd.Cmd):
    """Arista Fabric Initializer"""
    intro = 'Type ? for available commands' 
    prompt = 'builder>'
    
    def help_deploy(self):
        print('Use deploy NAME where NAME is the user-defined section with a defined recipe.')
    
    #check recipe syntax and variables
    def do_deploy(self, section):
        mode = searchConfig('mode', section)
        if mode == 'day2':
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
        
    def do_EOF(self, line):
        return True        

#get if dict, getattr if else
def searchSource(key, source, default = None):
    return source.get(key, default) if type(source) is dict else getattr(source, key, default)

def searchConfig(key, section = None):
    config = None
    if section:
        try:
            config = CONFIG.get(section, key).strip()
        except:
            pass
    if config == None:
        try:
            config = CONFIG.get('global', key).strip()
        except:
            return None

    if config.startswith('[') and config.endswith(']'):
        return [v.strip() for v in config[1:-1].split(',') if v]
        
    if config == 'True':
        return True
    if config == 'False':
        return False

    return config

def getKeyDefinition(key, source, section = None):
    csv_telemetry_source = key.split('#')
    
    file = None
    truncate = None
    op = None
    qty = None
    
    if len(csv_telemetry_source) == 2:
        
        file = csv_telemetry_source[0]
        key  = csv_telemetry_source[1]
    
    math = parseForMath(key)
    
    #can't truncate math op's; so either or
    if math:
        key, op, qty = math[0]
    else:
        key, truncate = parseForTruncation(key)[0]
        
    if truncate:
        start, end = truncate[1:-1].split(':')
        start = int(start) if start else None
        end = int(end) if end else None
    else:
        start = None
        end = None
    
    def truncateValues(values, start = None, end = None):
        if type(values) == list:
            return [str(val)[start:end] for val in values]
        else:
            return str(values)[start:end]

    def fetchTelemOrFileData(file, key):
        if file.startswith('/') and hasattr(CVP, 'cvprac'):
            #this is super hacked need a telemetry Data Model parser. cvp-connector has one but in js
            
            try:
                found = CVP.cvprac.get('/api/v1/rest/' + searchSource('sn', source, '').upper() + file)
                found = found['notifications'][0]['updates'][key]['value']
                if type(found) == dict:
                    __keys = found.keys()
                    if 'Value' in __keys:
                        found = found['Value']
                    elif 'value' in __keys:
                        found = found['value']
                    _type, val = found.items()[0]
                    return val
                else:
                    return found
            except:
                LOGGER.log("-failed to properly fetch/decode telemetry data")
                return None
        else:
            global SUPPLEMENT_FILES
            
            try:
                return SUPPLEMENT_FILES[file][key]
            except KeyError as e:
                pass
            try:
                with xlrd.open_workbook(file+'.xls') as f:
                    sheet = f.sheet_by_index(0)
                    sheet.cell_value(0,0)
                    
                    SUPPLEMENT_FILES[file] = {}
                    for col in range(sheet.ncols):
                        col = sheet.col_values(col)
                        col = [int(v) if type(v) == float else v for v in col]
                        SUPPLEMENT_FILES[file][col[0]] = col[1:]
                return SUPPLEMENT_FILES[file][key]
            except:
                return None
    
    if file:
        toReturn = fetchTelemOrFileData(file, key)
    elif key.isdigit():
        toReturn = key
    else:
        toReturn = searchSource(key, source) or searchConfig(key, section)
        if toReturn == 'ERROR' or not toReturn:
            toReturn = None
            
    if math:
        return (toReturn, op, qty)
    elif truncate:
        return truncateValues(toReturn, start, end)
    else:
        return toReturn


def parseForRequiredKeys(template):
    return re.findall('{(.*?)}', template)

def parseForIterables(template):
    return re.findall('\[[\s\S]*?\](?!else)', template)

def parseForSections(template):
    return re.findall('(@[\s\S]*?@)({.*?})*', template)

def parseForTruncation(key):
    return re.findall('([\w]+)(\([-+]?\d*:[-+]?\d*\))?', key)

def parseForMath(key):
    return re.findall('(\w+)([+\-*]+)(\d+)?', key)

#builds a tuple of values followed by a comparator lambda
#used to check if tests pass while supporting section injections from the global variable space
def buildConditionTest(keys):
    condition_list = []
    _keys = keys.split('&')
    
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
    return searchSource(sn.lower(), DEVICES)

def getByHostname(hostname):
    return searchSource(hostname.lower(), HOST_TO_DEVICE)

def buildGlobalData(injectSection = None):
    #INIT CONFIG
    loadConfig()
    
    global DEBUG
    DEBUG = searchConfig('debug', injectSection)
    
    #INIT TEMPLATES
    loadTemplates(injectSection)
    #INIT FABRIC CSV
    loadDevices(injectSection)
      
def loadConfig():
    global CONFIG
    CONFIG = {} 
    CONFIG = ConfigParser()
    CONFIG.read('global.conf')
    
def loadTemplates(injectSection = None):
    global TEMPLATES
    TEMPLATES = {}
    parser = ConfigParser()
    parser.read('templates.conf')
    for sectionName in parser.sections():
        TEMPLATES[sectionName] = Configlet(sectionName, dict(parser.items(sectionName)), injectSection)
    
def loadDevices(injectSection = None):

    global DEVICES
    global SPINES
    global ASSIGN_TO
    global COMPILE_FOR
    global HOST_TO_DEVICE

    
    DEVICES = {}
    SPINES = []
    ASSIGN_TO = []
    COMPILE_FOR = []
    HOST_TO_DEVICE = {}
    
    mode = searchConfig('mode', injectSection)
        
    _temp_vars = {}
    
    if mode == 'day2':
        spines = searchConfig('spines', injectSection)
        leafs = searchConfig('leafs', injectSection)
        compile_for = searchConfig('compile_for', injectSection)
        assign_to = searchConfig('assign_to', injectSection)
        
        follow_child_containers = searchConfig('follow_child_containers', injectSection)
        
        CVP.populate()
        
        spines = CVP.fetchDevices(spines, follow_child_containers) if spines else []
        leafs = CVP.fetchDevices(leafs, follow_child_containers) if leafs else []
        compile_for = CVP.fetchDevices(compile_for, follow_child_containers) if compile_for else []
        assign_to = CVP.fetchDevices(assign_to, follow_child_containers) if assign_to else []
        
        switch_vars = searchConfig('switch_vars', injectSection)
        if switch_vars:
            with xlrd.open_workbook(switch_vars) as f:
                sheet = f.sheet_by_index(0)
                sheet.cell_value(0,0)
                    
                headers = [val.lower() for val in sheet.row_values(0)]
    
                #row[0] is the serial
                #passing a dict to the switch to preserve csv headers
                for row in range(1, sheet.nrows):
                    sn_index = headers.index("sn")
                    row = sheet.row_values(row)
                    sn = row[sn_index].lower()
                    _temp_vars[sn] = dict(zip(headers,row))
                    
        #build the master list and label the implicit role for day2, since we don't know what's what
        
        for sn, cvp_device in CVP.devices.items():
            
            implicitRole = None
            if cvp_device in leafs:
                implicitRole = 'leaf'
            elif cvp_device in spines:
                implicitRole = 'spine'
            _temp_vars_device = searchSource(sn, _temp_vars, {})
            sn = sn.lower()
            hostname = (searchSource('hostname', _temp_vars_device, None) or cvp_device['hostname']).lower()
            
            DEVICES[sn] = Switch(_temp_vars_device, cvp_device, injectSection, implicitRole)
            HOST_TO_DEVICE[hostname] = DEVICES[sn]
            
            if implicitRole == 'spine':
                SPINES.append(DEVICES[sn])
            if cvp_device in compile_for:
                COMPILE_FOR.append(DEVICES[sn])
            if cvp_device in assign_to:
                ASSIGN_TO.append(DEVICES[sn])
            
    elif mode == 'day1':
        with xlrd.open_workbook(searchConfig('device_source', injectSection) or "fabric_parameters.xls") as f:
            sheet = f.sheet_by_index(0)
            sheet.cell_value(0,0)
                
            headers = [val.lower() for val in sheet.row_values(0)]

            #row[0] is the serial
            #passing a dict to the switch to preserve csv headers
            for row in range(1, sheet.nrows):
                sn_index = headers.index("sn")
                role_index = headers.index("role")
                row = sheet.row_values(row)
                sn = row[sn_index].lower()
                DEVICES[sn] = Switch(dict(zip(headers,row)), CVP.getBySerial(sn), injectSection)
                HOST_TO_DEVICE[DEVICES[sn].hostname.lower()] = DEVICES[sn]
                if row[role_index].lower() == "spine":
                    SPINES.append(DEVICES[sn])
    
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