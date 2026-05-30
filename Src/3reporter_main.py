import os
import sys
import string
from math import fabs
import ConfigParser

'''The data structures contain the following information (eventually):
####Control-a dictionary used to hold information
enableXRA, enableFLA: Are flags that determine whether XRA/FLA analysis will be included. Default False
enableINIUpdate: Flag to determine whether the Observers file will be updated based on this report. Default: False
path: Path to directory for output, which is usually the place for input
month: Three letter month
year: Two digit year
HiQualLimit: Minimum observer quality ratio required to include uncorrelated events in report
nObservers: The number of Observers that have had a file read for analysis
nEvents: Total number of submitted events
nCorr: Number of correlated events
nImp: List to hold the number of each importance level in the correlations

####OBSERVER-a class to hold observer information and reports for analysis
ID: a numerical ID 
id: ID code in string format. Begins with 'A'
name: Observer name
ngdcName: First initial, Last name
location: City, State or City, Country
quality: Quality rating for observer. Changes over time
qualCount: Number of reports used to generate quality rating
nReports: Number of reports submitted for this analysis
reports: A list that holds a dictionary for each report
---methods are described elsewhere

####report-a dictionary for each report submitted for analysis
path: Full path to data file
filen: Name of file
station: Station code and frequency
nEvents: Number of events reported
unusedEvents: Number of events that are uncorrelated
qualRatio: (correlated events)/(total events)*10
events: A list of event dictionaries

####event-a dictionary for each event in a report
strEvent: The event string as read from the data
importance: Event importance rating. A string of for n*, n is 1,2 or 3; * is -,+, or absent
day: Numerical day of event
peakTime: Peak event time (UT in minutes as 0-1440)
difference: Time difference in minutes from peak time
duration: (Stop time)-(Start time)
crFlag: An integer used to signal if event has been correlated and the type of correlation

####XRA-a dictionary to describe XRA events
day: Integer day of event
peak: Peak event time (UT in minutes as 0-1440)
duration: (Stop time)-(Start time)
strength: String to indicate X-Ray event strength (from data)
strengthN: Numerical version of strength

####FLA-a dictionary to describe FLA events
day: Integer day of event
peak: Peak event time (UT in minutes as 0-1440)
duration: (Stop time)-(Start time)

####CORR_EVENT-a dictionary used to store information on correlations
importance: 
day:
peak:
count:
userID:
crFlag:
'''


Control_dict = {'enableXRA':False, 'enableFLA':False, 'HiQualLimit':10, 'enableINIUpdate':False, 'nObservers':0, 'nEvents':0, 'nCorr':0, 'nImp':[], 'path':''}
OBSERVERS_INI= 'SIDAnalObservers.ini'
STATION_INI= 'SIDAnalStations.ini'
FALSE = 0
TRUE = 1
#Flags to indicate how event correlation was determined
USER_CORRELATED   =      1
XRA_CORRELATED    =      2
FLA_CORRELATED    =      3
HIQUAL_CORRELATED =      4
#Database modes. Could use strings.
DB_FULL = 0
DB_PARTIAL = 1
#-------------------------------------------
def prompt_month_year():
    '''Returns the raw_input function with a request for date information. 
    Written as a function to facilitate unit testing of SetUpDefaultDirectory'''
    return raw_input('\n Enter 3 character month and 2 digit year (any number of characters between them): \nExamples: Jun11, Jun 11, Jun...11: ')

def SetUpDefaultDirectory(Control_dict, input_func=prompt_month_year):
    '''Takes in the control dictionary and a function requesting month and year of observation data.
 Updates the dictionary
    containing the control information with the month, year, and the path to the directory for reports'''
    
    #Gets the month and year in three letter month, 2 digit year format with arbitrary characters in between
    mmmyy = input_func()

    if len(mmmyy)>=5:
        #Extract and test month
        mmm=mmmyy[0:3]
        if str.isalpha(mmm):
            mmm=mmm.upper()
        else:
            sys.exit("\n Invalid date: month field not all characters \n")

        #Extract and test year
        yy=mmmyy[-2:]
        if not str.isdigit(yy):
            sys.exit("\n Invalid date: year field is not an integer \n")
    else:
        sys.exit('\n Invalid entry\n')
        
    #Create date in proper format
    date = mmm + '_' + yy

    path=os.path.join(Control_dict['path'], date, 'Data Received')
    if not os.path.exists(path):
        os.makedirs(path)
        
    #Update the control dictionary
    Control_dict['month']=mmm
    Control_dict['year']=yy
    Control_dict['path']=os.path.join(Control_dict['path'], date, 'Data Received')
#-------------------------------------------
    
def GetFiles():
    '''Very basic tkinter file choice dialog to select files'''
    import Tkinter, tkFileDialog
    root = Tkinter.Tk()
    files = tkFileDialog.askopenfilenames(parent=root, title='Choose Observer files', filetypes = [('Observer files', ('*.dat'))])
    files = root.tk.splitlist(files)
    root.destroy()
    #Return a tuple of files
    return files

#-------------------------------------------
def SID_reporter(OBSERVERS_INI='SIDAnalObservers.ini',STATION_INI='SIDAnalStations.ini'):
    '''This is the function entered after the command line arguments are parsed. 
    Most other functions are called from within this one'''
    
    #Get the month and year from the user and set up the path
    #Use 'prompt_month_year' in order to facilitate unit test
    SetUpDefaultDirectory(Control_dict)

    #What to do with XRA/FLA data
    goes_ans=raw_input("Use GOES Data Correlation? y/[n]: ")
    if goes_ans.lower()=='y':
        Control_dict['enableXRA']=True
        Control_dict['enableFLA']=True
        print 'Using GOES data correlation\n'

    #Setting HiQualLimit
    HiQualLimit=raw_input('Set Observer Minimum Quality Rating to include uncorrelated events\nreported by a single observer: [10] ')
    if not str.isdigit(HiQualLimit):
        HiQualLimit=10
    else:
        HiQualLimit=int(HiQualLimit)
    print 'Minimum Quality Rating: {}\n'.format(HiQualLimit)

    if HiQualLimit==0:
        response=raw_input("Type 'Y' to confirm Minimum Quality Rating of 0: ")
        if not response=='Y':
            HiQualLimit=10
    Control_dict['HiQualLimit']=HiQualLimit

    #Choose whether OBSERVERS_INI file should be updated with quality statistics from this analysis
    response=raw_input("Update {} file based on this analysis? y/[n] ".format(OBSERVERS_INI))
    if response.lower()=='y':
        Control_dict['enableINIUpdate']=True
        print '{} will be updated.'.format(OBSERVERS_INI)
        
    #Select reports
    print 'The program will generate DatabaseFullSumm.csv and SIDDatabase_{0}.\n\
Use the numbers below to select other reports by typing a comma separated list.\n\
1-SIDngdc_{0} 2-SIDDatabaseFull_{0} 3-SID_DatabaseFull_Sum 4-SID_Database_Sum 5-Observers Summary *-All reports\n'.format((Control_dict['month'].upper()+Control_dict['year']))
    response=raw_input("Enter your choices [none]: ")
    response=response.split(',')
    Control_dict['response']=response
    
    #Get names of Observer files
    files = GetFiles()

    if len(files)!=0:

        #Populate array of Observer class objects
        Observers=ReadReports(files, Control_dict, OBSERVERS_INI)



        #Get XRA data set
        if Control_dict['enableXRA']:
            xra=ReadXRA(Control_dict)
            
        #Get FLA data set
        if Control_dict['enableFLA']:
            fla=ReadFLA(Control_dict)

        #Search for Event correlations
        #Correlate observer to observer events within 5 minutes of each other
        #CORR_EVENT dict {'importance':'', 'day':'', 'peak':'', 'count':'', 'userID':'', 'crFlag':''}
        Corr=CorrelateObservers(5, Control_dict, Observers)
        #Get leftover events that are within 15 minutes of a correlated event
        Corr=CompareObserversToCorrList(15, Control_dict, Observers, Corr)
        
        #XRA and FLA
        if Control_dict['enableXRA']:
            Control_dict['nCorr']+= CompareToXRAFLA(15, Control_dict, Observers, Corr, xra, XRA_CORRELATED)

        if Control_dict['enableFLA']:
            Control_dict['nCorr']+= CompareToXRAFLA(15, Control_dict, Observers, Corr, fla, FLA_CORRELATED)
            
        #Calculate qualRatio for each report. OBSERVERS_INI may be modified if modification has been enabled
        ComputeUnusedObserverEvents(Control_dict,Observers,Control_dict['enableINIUpdate'])
        #Get events that are uncorrelated but from trusted observers with a default quality rating of 10
        if Control_dict['HiQualLimit']<10:
            Control_dict['nCorr'] += DetectHiQualNonCorrelatedEvents(Control_dict, Observers, Corr)

        #Data Output -- Events and Stats
        #Sort correlated events
        Corr=sorted(Corr,cmp=SortCorrelationList)
        
        #Write out data files
        GenerateDatabaseFile(Control_dict, Observers, Corr, DB_PARTIAL)
        if '1' in response or '*' in response:
            GenerateNGDC_File(Control_dict,Observers)
        if '2' in response or '*' in response:
            GenerateDatabaseFile(Control_dict, Observers, Corr, DB_FULL)
        if '5' in response or '*' in response:
            GenerateFileOfUnusedObserverEvents(Control_dict,Observers)

#-------------------------------------------
def ReadReports(files, Control_dict, OBSERVERS_INI):
    '''Takes the selected data files and extracts information on the observers.
    Creates OBSERVER objects and populates their reports (a list of dictionaries) with events (a list of dictionaries).
    Returns list of OBSERVER objects.
    '''
    def inputname():
        return raw_input("Enter full name...")

    def inputlocation():
        return raw_input("Enter observer's location; format: City,State")
    
    #List of OBSERVER objects to be returned and an index
    obs_objs=[]
    obs_index=0
    
    #List of observer IDs
    obs_id_list=[]
    
    for f in files:
        #Split file path into path and name
        filename = os.path.split(f)
        #Get the basename for the file
        filename=os.path.splitext(filename[1])[0]
        #Get what should be the integer portion of the observer id from the name
        intID=filename[1:-3]
        #Print something to screen if it is not an integer
        if not str.isdigit(intID):
            print "Incorrect intID: {}".format(intID)
        else:
            intID=int(intID)
        #Get what should be the observer ID string
        strID=filename[0:-3]
        #Get what should be the station name
        strSTA=filename[-3:]
        #Print something to screen if it is not alpha
        if not str.isalpha(strSTA):
            print "Incorrect strSTA: {}".format(strSTA)
       
        #Search in observer id list for observer ID
        if not (intID in obs_id_list):
            #If not in list, initialize an OBSERVER object
            #This should be later if checks on number of records and events are needed
            obs_objs.append(OBSERVER(intID,strID,strSTA))
            obs_objs[obs_index].GetObserverInfo(OBSERVERS_INI)
            #Update the ID list
            obs_id_list.append(intID)
            #Increment the number of observers in the run
            Control_dict['nObservers']+=1            
            #Set up first report
            #obs_objs[obs_index].reports.append({}) ###Moved lower into actions for all. Probably won't work with 2 or more reports like this
            obs_index+=1

        #These steps are done for every intID, new or previously on the list
        #Find index of obs_obj list associated with intID
        index=obs_id_list.index(intID)
        #obs_objs[index].reports.append({})
        report_index=obs_objs[index].nReports
        #Sets up the report dictionary in the observer object
        obs_objs[index].init_report(strSTA,f)
        #Get the events for this report
        obs_objs[index].get_events(report_index)

    obs_objs.sort(key=lambda obs: obs.id)
    return obs_objs

#-------------------------------------------
class OBSERVER():
    '''This class holds observer information (name, ID, station, etc). Much of this is gathered with
    the method GetObserverInfo. The class holds reports and their information, including events. Obtaining this
    uses the methods init_reports, GetReportInfo, and get_events.'''
    
    def __init__(self, ID, strID, strSTA):
        self.ID=ID
        self.id=strID
        self.strSTA=strSTA
        self.nReports=0
        #self.reports will hold a list of dictionaries, one for each report
        #{'path':'', 'file':'', 'station':'', 'nEvents':0, 'unusedEvents':0, 'qualRatio':0, 'events':[]}
        self.reports=[]

    #Added for unit testing
    def inputname():
        return raw_input("Enter full name... ")

    def inputlocation():
        return raw_input("Enter observer's location; format: City, State: ")
    
    def GetObserverInfo(self,OBSERVERS_INI,get_name=inputname,get_location=inputlocation): #get name, location, quality rating; create entry for new observers
        config=ConfigParser.RawConfigParser()
        config.optionxform = str
        #obs_file=os.path.join(os.getcwd(), OBSERVERS_INI)
        obs_file=OBSERVERS_INI
        config.read(obs_file)
        try:
            ngdcName=config.get('NGDC NAME', self.id)
        except:
            with open(obs_file, 'w') as configfile:
                print "No data exists in {} for {}\n".format(OBSERVERS_INI, self.id)
                name=get_name()
                config.set('NAME', self.id, name)
                ngdcName=name.lstrip()[0]+' '+name.split()[1]
                config.set('NGDC NAME',self.id,ngdcName)
                location=get_location()
                config.set("LOCATION", self.id, location)
                config.set('QUALITY RATING', self.id, 0)
                config.set('QUALITY COUNT', self.id, 0)
                config.write(configfile)

        self.name=config.get('NAME', self.id)
        self.ngdcName=config.get('NGDC NAME', self.id)
        self.location=config.get('LOCATION',self.id)
        self.quality=int(config.get('QUALITY RATING',self.id))
        self.qualCount=int(config.get('QUALITY COUNT',self.id))

    def init_report(self,strSTA,filepath,stations=STATION_INI):
        '''Initializes a report dictionary'''
        report={'path':filepath, 'filen':os.path.split(filepath)[1], 'station':'', 'nEvents':0, 'unusedEvents':0, 'Events':[]}
        report['station']=self.GetReportInfo(strSTA,stations)
        self.reports.append(report)

    def GetReportInfo(self, strSTA, STATION_INI, input_func=None):
        '''Gets frequency information. Updates STATION_INI file if necessary'''

        def prompt_station_freq():
            return raw_input("Enter VLF station frequency (KHz)...")

        if input_func==None:
            input_func=prompt_station_freq

        config=ConfigParser.RawConfigParser()
        config.optionxform = str
        config.read(STATION_INI)
        try:
            station=config.get('FREQUENCY', strSTA)
        except:
            with open(STATION_INI, 'w') as configfile:
                while True:

                    print "No Frequency Reference in {} for {}\n".format(STATION_INI, strSTA)
                    #A little contortion for unit testing
                    station=input_func()
                    if not str.isalpha(station):
                        break
                    else:
                        print "Input valid entry; there should be no letters. Using ****\n"
                        station='****'

                config.set('FREQUENCY', strSTA, station+'khz ('+strSTA+')')
                config.write(configfile)
            
        station=config.get('FREQUENCY', strSTA)

        return station

    def get_events(self,report_index):
        '''Takes a report and gets event information.
        Returns the number of events and the list of events'''

        '''def TimeAscii2int(s):
            #Converts ascii time to integer time (0-1440)
    
            if not str.isdigit(s):
                return 0

            hr=int(s[0:2])
            min=int(s[2:])

            time=hr*60+min

            return time'''

        report=self.reports[report_index]
        events=[]
        index=0
        problem_files=[]

        #Dictionary to map importance parameter from SES event line to a number
        importance_map={'1-':0,'1':1,'1+':2,'2':3,'2+':4,'3':5,'3+':6}

        #filen=os.path.join(report['path'],report['filen'])
        with open(report['path'], 'r') as file:
            problem_entry=0
        #with open(filen, 'r') as file:
            for line in file:
                
                #---------
                fields=line.split()
                if len(fields)==0 or fields[0]!='40':
                    continue

                #Count lines with event data
                problem_entry+=1
                #---------
                #Assumes any problems with the string is from presence of characters D, E, or U appended to
                #one of the first two times. Ignores the characters to continue with extracting information.
                if len(fields)!=8:
                    tmpline=line
                    for x in ['D','E','U']:
                        tmpline=tmpline.replace(x,' ')
                    fields=tmpline.split()
                #---------
                tmp={}
                #events.append({})
                #Store event string
                #events[index]['strEvent']=line.rstrip()
                try:
                    #Get day
                    tmp['day']=int(fields[1][-2:])
                    #Get peak time
                    tmp['peakTime']=TimeAscii2int(fields[4][:4])
                    #Get importance rating
                    tmp['importance']=importance_map[fields[5][:2]]
                    #Find duration
                    tmp['duration']=TimeAscii2int(fields[3][:4])-TimeAscii2int(fields[2][:4])
                    #Set flag to indicate it has not been correlated
                    tmp['crFlag']=FALSE

                    #Assuming all of the above has been successful, create an event
                    events.append({})
                    #Copy the information from tmp
                    events[index]=tmp
                    #Store the event string
                    events[index]['strEvent']=line.rstrip()
                    #increment the event index
                    index+=1
                except:
                    #If things have not gone well, append to list of problem files
                    #Currently not used
                    problem_files.append((os.path.split(report['path'])[1],problem_entry))
                    #Print to screen
                    print '{} has an unexpected event string, entry {}'.format(os.path.split(report['path'])[1],problem_entry)
                    
        #print index
        self.reports[report_index]['nEvents']+=index
        #print self.reports[report_index]['nEvents']
        self.reports[report_index]['Events']=events
        #After adding the events to a report, increment the number of reports
        self.nReports+=1

    def __eq__(self,other):

        try:
            if [attr for attr in self.__dict__.keys()].sort()==[attr for attr in other.__dict__.keys()].sort():
                ls=[self.__dict__[b] == other.__dict__[b] for b in [attr for attr in self.__dict__.keys()]]
            
                if False in ls:
                    return False
                else:
                    return True
            else:
                return False
        except:
            return False
        
    def __str__(self):

        keys=self.__dict__.keys()
        keys.sort()
        string = ''
        for k in keys:
            string += k + ':' + str(self.__dict__[k]) + ','
        return string[:-1]
            
#-------------------------------------------
def CorrelateObservers(timerange, Control_dict, obs_objs):
    '''Side effect: Updates obs_objs'''
    
    #corr_event={'importance':0, 'day':0, 'peak':0, 'count':0, 'userID':'', 'crFlag':''}
    corr_events=[]
    cIdx=Control_dict['nCorr']
    
    for obs in obs_objs:
        oind=obs_objs.index(obs)
        for report in obs.reports:
            for event in report['Events']:
                #Try to correlate event if flag has not been set
                if event['crFlag']==FALSE:
                    corrFound = False
                    avePeak = event['peakTime']
                    aveCount =1

                    #Iterate over events in the remaining reports of the current observer
                    #and all reports of the other observers. 
                    #This is a first pass to gather data for an average.
                    #Only one correlated event per observer will be used.
                    #
                    sind=1+obs.reports.index(report) #To start search in current observer's next record
                    
                    for obs2 in obs_objs[oind:]:
                        for report2 in obs2.reports[sind:]:
                            mIdx=MatchEvent(timerange, event['day'],event['peakTime'],report2['Events'])
                            # -1 indicates no match was found
                            if mIdx != -1:
                                corrFound = True
                                avePeak += report2['Events'][mIdx]['peakTime']
                                aveCount+=1
                                break #Match found in report. Skip other reports from current observer
                        sind=0 #To have subsequent searches go over all records of an observer
                        
                    #Iterate over the same list of reports comparing to the "average" of all matches so far
                    #This allows program to find events with peaks>5 minutes from initial event
                    #but <5 minutes from average of the majority of matching events
                    if(corrFound):
                        avePeak=(avePeak)/aveCount

                        #Iterate each event of all other observers after the current observer??
                        #I believe this just goes over all observers and checks that crFlag has not been set to True
                        for obs2 in obs_objs:   #Otherwise this would be 'for obs2 in obs_objs[oind+1:]'
                            for report2 in obs2.reports:
                                mIdx=MatchEvent(timerange, event['day'],avePeak,report2['Events'])
                                if mIdx != -1:
                                    #If this is the first match for the event, set parameters
                                    if not event['crFlag']:
                                        corr_events.append({})
                                        corr_events[cIdx]['importance']=event['importance']
                                        corr_events[cIdx]['day']=event['day']
                                        corr_events[cIdx]['peak']=event['peakTime']
                                        corr_events[cIdx]['crFlag']=USER_CORRELATED
                                        corr_events[cIdx]['count']=1
                                        event['crFlag']+=1

                                    #mIdx is index of matching event in report2['Events']
                                    corr_events[cIdx]['importance']+=report2['Events'][mIdx]['importance']
                                    corr_events[cIdx]['peak']+=report2['Events'][mIdx]['peakTime']
                                    corr_events[cIdx]['count']+=1
                                    report2['Events'][mIdx]['crFlag']+=1
                                    continue

                        corr_events[cIdx]['importance'] = corr_events[cIdx]['importance']/corr_events[cIdx]['count']
                        corr_events[cIdx]['peak'] = corr_events[cIdx]['peak']/corr_events[cIdx]['count']
                        cIdx+=1
                        #End of correlation of current event to other observer
    Control_dict['nCorr']=cIdx
    return corr_events
#-------------------------------------------
def MatchEvent(timerange, day, pkTime, eventlist):

    mIdx=-1
    
    for event in eventlist:
        if not event['crFlag']:
            if event['day'] == day:
                if abs(event['peakTime']-pkTime) <= timerange:
                    mIdx=eventlist.index(event)
                    break
    return mIdx

#-------------------------------------------
def CompareObserversToCorrList(timerange, Control_dict, obs_objs, corr_event):
    '''Side effect: Updates obs_objs'''
    
    #Iterate over each event of every report for all observers
    for obs in obs_objs:
        oind=obs_objs.index(obs)
        for report in obs.reports:
            for event in report['Events']:
                #Check if flag has not been set
                if not event['crFlag']:
                    corrFound=False
                    for corr in corr_event[oind+1:]:
                        if corr['day']==event['day']:
                            if (abs(corr['peak']-event['peakTime'])<=timerange):
                                #Compute the new average peak
                                corr['peak'] = (corr['peak']*corr['count']+event['peakTime'])/(corr['count']+1)
                                #Compute the new average importance
                                corr['importance'] = (corr['importance']*corr['count']+event['importance'])/(corr['count']+1)
                                #Update the count
                                corr['count']+=1
                                #Set the correlation flag
                                event['crFlag']+=1
    return corr_event
#-------------------------------------------
def ComputeUnusedObserverEvents(Control_dict, obs_objs, updateObserverQual):
    '''Side effect: Updates obs_objs'''
    
    #Get file handle for OBSERVER_INI

    for obs in obs_objs:
        #if obs.id[2]=='4' or obs.id=='A116':
            #print obs
        for report in obs.reports:
            unused=0
            for event in report['Events']:
                if event['crFlag']==False:
                    unused+=1
            report['unusedEvents']=unused
            #print obs.nReports,report['nEvents'],unused,obs.id
            if report['nEvents']!=0:
                report['qualRatio']=int((report['nEvents']-unused)/float(report['nEvents'])*10)
            else:
                report['qualRatio']=0
            #Only update Observer quality of requested by the calling function
            #Don't update if report quality <=2 since this usually indicate an observer made
            #a mistake in report generation or submittal and should not be penalized.
            if updateObserverQual and report['qualRatio']>2:
                obs.quality = (obs.quality*obs.qualCount+report['qualRatio'])/(obs.qualCount +1)
                obs.qualCount+=1
                config=ConfigParser.RawConfigParser()
                config.optionxform = str
                config.read(OBSERVERS_INI)
                config.set('QUALITY RATING', obs.id, str(obs.quality))
                config.set('QUALITY COUNT', obs.id, str(obs.qualCount))
                with open(OBSERVERS_INI, 'w') as configfile:                
                    config.write(configfile)

#-------------------------------------------
def SortCorrelationList(item1,item2):

    if item1['day'] < item2['day']:
        return -1
    elif item1['day'] > item2['day']:
        return 1

    if item1['peak'] < item2['peak']:
        return -1
    elif item1['peak'] > item2['peak']:
        return 1

    return 0

#-------------------------------------------
def GenerateNGDC_File(Control, obs_objs):

    #Set up date
    month=MonthStr(Control['month'])
    moYear=month+',20'+str(Control['year'])
    
    #Filename
    file=os.path.join(Control['path'],'SIDngdc_'+month+Control['year']+'.txt')

    with open(file, 'w') as fh:
        #Heading
        fh.write('                         Sudden Ionospheric Disturbance Report\n')
        fh.write('                                    -- {} --\n\n'.format(moYear))

        #Observer information
        for obs in obs_objs:
            f=0
            for report in obs.reports:
                #Get name and observer ID
                if f==0:
                    observer='{} {}, {} - '.format(obs.id, obs.ngdcName, obs.location)
                #Append monitored station to observer info
                observer='{} {} '.format(observer, report['station'])
                f=1
            observer=observer+'\n\n'
            fh.write(observer)

        #Correlated events
        listEvents=[]
        for obs in obs_objs:
            for report in obs.reports:
                for event in report['Events']:
                    if event['crFlag']:
                        listEvents.append(event['strEvent'])
        #The sort is done on the year, month, day,and time in characters 5-17
        #and the observer id string in characters 69-73
        listEvents=sorted(listEvents,key=lambda s: s[5:18]+s[69:74])

        for event in listEvents:
            fh.write('\n'+event)

        #Termination
        fh.write('\n\n-- End Report --')
            
#-------------------------------------------
def TimeInt2ascii(time):
    
    min=time%60
    hour=time/60

    return '{:02}{:02}'.format(hour,min)
#-------------------------------------------
def SetDateForDBFile(year, month, day):

    mnum=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
    strDat=str(year)+'{:02}'.format(mnum.index(month.lower())+1)+'{:02}'.format(int(day))
    return strDat
#-------------------------------------------    
def MonthStr(month):
    mtxt={'jan':"January",'feb':"February",'mar':"March",'apr':"April",'may':"May",'jun':"June",'jul':"July",'aug':"August",'sep':"September",'oct':"October",'nov':"November",'dec':"December"}

    return mtxt[month.lower()]
#-------------------------------------------
def GenerateDatabaseFile(Control,obs_objs,corr_event,mode):

    #Dictionary for getting crType
    crType={0:"",1:"XRA",2:"FLA",3:"QUAL"}
    
    #Set up date formats
    month=Control['month']
    month=month.replace(month[0],month[0].upper())
    mnum=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
    mm='{:02}'.format(mnum.index(Control['month'].lower())+1)
    year='20'+Control['year']
    moYear=month+' '+year

    if mode==DB_PARTIAL:
        file=os.path.join(Control['path'],'SIDDatabase_'+month+Control['year']+'.txt')
    else:
        file=os.path.join(Control['path'],'SIDDatabaseFull_'+month+Control['year']+'.txt')

    csvfile=os.path.join(Control['path'],year+mm+'DatabaseFullSumm.csv')

    with open(file,'w') as fh:
        #Heading
        fh.write('AAVSO Sudden Ionospheric Disturbance Report')
        fh.write('\n{} {}\n\nObservers:\n'.format(month,year))

        #Observer IDs
        k=Control['nObservers']/2
        line1= 1 if k==0 else k+Control['nObservers']%k
        line2= 0 if k==0 else k
        k=0
        for i in range(line1):
            fh.write(obs_objs[k].id+'\t')
            k+=1
        fh.write('\n')
        for i in range(line2):
            fh.write(obs_objs[k].id+'\t')
            k+=1

        #Data
        fh.write('\n\nYYMMDD          Event Peak              Importance')

        for corr in corr_event:
            if mode==DB_PARTIAL:
                if corr['crFlag'] == USER_CORRELATED or\
                   corr['crFlag'] == HIQUAL_CORRELATED or\
                   (corr['crFlag'] == XRA_CORRELATED and corr['peak'] <= 600) or\
                   (corr['crFlag'] == FLA_CORRELATED and corr['peak'] <= 600):
                    fh.write('\n{}\t\t{}\t\t\t{}'.format(SetDateForDBFile(Control['year'],Control['month'],corr['day']),\
                                                                          TimeInt2ascii(corr['peak']),
                                                                          FileSetImp(corr['importance'])))
                if mode==DB_FULL:
                    fh.write('\n{}\t\t{}\t\t\t{}'.format(SetDateForDBFile(Control['year'],Control['month'],corr['day']),\
                                                                          TimeInt2ascii(corr['peak']),
                                                                          FileSetImp(corr['importance'])))
                    if corr['count']==1:
                        fh.write('\t{} '.format(corr.userID))
                        fh.write(' - {}'.format(crType[corr['crFlag']-1]))

        #Event Summary
        #Sum the number of events per importance level. Write out to the DB
        total=SumImportanceLevels(Control, corr_event, mode)
            
        fh.write('\n\n\n\n**************************************************')
        fh.write('\nImportance Summary - {}'.format(moYear))
        for i in range(7):
            fh.write('\n\t{:2s} events: {:2d}'.format(FileSetImp(i), Control['nImp'][i]))
        fh.write('\n ------------------\n   Total events: {:02d}'.format(total))

    with open(csvfile,'w') as csvfh:
        for i in range(7):
            csvfh.write('\n\t{:2s},{:2d}'.format(FileSetImp(i), Control['nImp'][i]))

    #Generate summary file
    if ('3' in Control['response'] and mode== DB_FULL) or ('4' in Control['response'] and mode == DB_PARTIAL) or '*' in Control['response']:
        GenerateAnalysisSummaryFile(Control,obs_objs,corr_event,mode,moYear)
#-------------------------------------------
def SumImportanceLevels(Control, corr_event,mode):
    Control['nImp']=[]
    total=0
    
    for i in range(7):
        sum=0
        for corr in corr_event:
            if corr['importance']==i:
                if mode==DB_PARTIAL:
                    if corr['crFlag']==USER_CORRELATED or\
                       corr['crFlag']==HIQUAL_CORRELATED or\
                       (corr['crFlag']==XRA_CORRELATED and corr['peak']<=600) or\
                       (corr['crFlag']==FLA_CORRELATED and corr['peak']<=600):
                        sum+=1

                if(mode==DB_FULL):
                    sum+=1

        Control['nImp'].append(sum)
        total+=sum
        
    return total
#-------------------------------------------
def GenerateAnalysisSummaryFile(Control,obs_objs,corr_event,mode,moYear):

    #Dictionary for text version of mode
    md={0:'FULL',1:'PARTIAL'}
    
    file=Control['path']
    if mode==DB_PARTIAL:
        file=os.path.join(file,'SID_Database_Sum.txt')
    else:
        file=os.path.join(file,'SID_DatabaseFull_Sum.txt')

    with open(file,'w') as fh:
        fh.write('Data Analysis Summary file   -  {}, {}\n'.format( MonthStr(Control['month']), '20'+str(Control['year'])))
        if Control['enableXRA'] or Control['enableFLA']:
            fh.write('\n\nSecondary correlation with GOES XRA, FLA Data was performed')
            if mode==DB_PARTIAL:
                fh.write('\n  XRA, FLA correlated events included in analysis only if event time < 1000 UT')
            else:
                fh.write('\n  All XRA, FLA correlated events included in this listing')

        fh.write('\n\nUncorrelated events included for observers with a quality rating >= {:d}'.format(Control['HiQualLimit']))

        #Importance level summary
        fh.write('\n\nImportance Summary - {}  {}'.format(moYear, md[mode]))
        fh.write('\n\nImportance\tCount')
        for i in range(7):
            fh.write('\n{:2s} \t\t{:2d}'.format(FileSetImp(i), Control['nImp'][i]))

        #Contributing observers
        #Observer information
        fh.write('\n\n\n\nContributing Observers\n')
        for obs in obs_objs:
            f=0  #set to trigger set up of observer information in first report
            for report in obs.reports:
                if f==0:
                    observer='\n{}{}\t{}\t'.format(obs.ngdcName, 10*' ', obs.id) 
                #Append station information to observer info
                #observer=observer+report['station'][:-1].replace('(','')+' ' #Concatenate previous information with station information [without parentheses]
                observer=observer+report['station'].split()[1][1:-1]+' ' #Concatenate previous information with station call sign
            fh.write(observer)
            f=1

        #GOES-8 Flare class summary
#-------------------------------------------
def GenerateFileOfUnusedObserverEvents(Control, obs_objs):

    #Don't request update of INI file because results AT THIS POINT in analysis 
    #may include events correlated based on a prior HI-Quality rating. 
    #The INI file has already been updated with the results from current report,
    #before the optional HI-Quality rating
    ComputeUnusedObserverEvents(Control, obs_objs, FALSE);
    
    file=Control['path']
    file=os.path.join(file,'Observers Summary.txt')

    with open(file,'w') as fh:

        #Heading
        fh.write('SID OBSERVER Unused Event Summary  -  {}, {}\n'.format(MonthStr(Control['month']), '20'+str(Control['year'])))
        fh.write('\n\nMinimum observer quality rating used in analysis - [{}]'.format(Control['HiQualLimit']))
        fh.write('\n\nObserver quality rating based on correlated events only, \nnot events included due to previous hiqh quality rating.')

        for obs in obs_objs:
            fh.write('\n\nObserver: {:4}   -   {}\t\t\tQuality Rating: {} for {} reports'.format(obs.id,obs.name,obs.quality,obs.qualCount))
            for report in obs.reports:
                fh.write('\n    Station: {} '.format(report['station']))
                fh.write('\n      Quality Rating: [{:2d}]'.format(report['qualRatio']))
                fh.write('\n        Total events:  {:2d}'.format(report['nEvents']))
                fh.write('\n       Unused events:  {:2d}'.format(report['unusedEvents']))
                if report['unusedEvents']:
                    for event in report['Events']:
                        if not event['crFlag']:
                            fh.write('\n        {}'.format(event['strEvent']))

#-------------------------------------------
def FileSetImp(n):
    
    #Dictionary for converting numerical importance to numerical and symbol
    importance_map={0:'1-',1:'1',2:'1+',3:'2',4:'2+',5:'3',6:'3+'}

    return importance_map[n]

#-------------------------------------------
def ReadXRA(control):
    #dictionary to convert 'strength' to 'strengthN'
    class_strength={'A':1,'B':10,'C':100,'M':1000,'X':10000}
    ind=0
    xra=[]
    filename=os.path.join(control['path'],'{}_{}XRA.txt'.format(control['month'],control['year']))
    with open(filename,'r') as fh:
        for line in fh:
            if str.isdigit(line[0]):
                xra.append({})
                xra[ind]['day']=int(line[3:5])
                xra[ind]['peak']=TimeAscii2int(line[17:21])
                xra[ind]['duration']=TimeAscii2int(line[24:28])-TimeAscii2int(line[10:14])
                xra[ind]['strength']=line[35:40]
                xra[ind]['strengthN']=class_strength[line[35:36]]*float(line[36:39])  #StrengthAscii2int(xra[ind]['strength'])
                ind+=1
    xra.append({})
    xra[ind]['day']=-1
    return xra
#-------------------------------------------
def ReadFLA(control):
    ind=0
    fla=[]
    filename=os.path.join(control['path'],'{}_{}FLA.txt'.format(control['month'],control['year']))
    with open(filename,'r') as fh:
        for line in fh:
            if str.isdigit(line[0]):
                fla.append({})
                fla[ind]['day']=int(line[3:5])
                fla[ind]['peak']=TimeAscii2int(line[17:21])
                fla[ind]['duration']=TimeAscii2int(line[24:28])-TimeAscii2int(line[10:14])
                ind+=1
    fla.append({})
    fla[ind]['day']=-1
    return fla

#-------------------------------------------
def TimeAscii2int(s):
    '''Converts ascii time to integer time (0-1440)'''

    if not str.isdigit(s):
        return 0

    hr=int(s[0:2])
    min=int(s[2:])

    time=hr*60+min

    return time

#-------------------------------------------
def CompareToXRAFLA(timerange, control, obs_objs, corr, xrafladata, STATUS_STRING):

    cIdx=control['nCorr']
    
    for obs in obs_objs:
        for report in obs.reports:
            for event in report['Events']:
                if not event['crFlag']:
                    corrFound = MatchXRAFLAEvent(timerange, event['day'], event['peakTime'], xrafladata) #MatchXRAEvent(timerange, event['day'], event['peakTime'], xra)
                    if corrFound:
                        corr.append({})
                        corr[cIdx]['importance'] = event['importance']
                        corr[cIdx]['day'] = event['day']
                        corr[cIdx]['peak']= event['peakTime']
                        corr[cIdx]['count']= 1
                        corr[cIdx]['userID'] = obs.ID
                        corr[cIdx]['crFlag'] = STATUS_STRING #XRA_CORRELATED/FLA_CORRELATED
                        cIdx+=1
                        event['crFlag']= STATUS_STRING #XRA_CORRELATED/FLA_CORRELATED

    return (cIdx-control['nCorr'])
#-------------------------------------------
def MatchXRAFLAEvent(timerange, day, pkTime, xrafladata):

    match=False
    ind=0

    while xrafladata[ind]['day']!=-1 and xrafladata[ind]['day'] <= day and not match:
        if xrafladata[ind]['day']==day:
            if abs(xrafladata[ind]['peak']-pkTime) <= timerange:
                match = True
        ind+=1
    
    return match

#-------------------------------------------
def DetectHiQualNonCorrelatedEvents(Control, obs_objs, corr):

    cIdx=Control['nCorr']

    for obs in obs_objs:
        if obs.quality >= Control['HiQualLimit'] or Control['HiQualLimit==0']:
            for report in obs.reports:
                if report['qualRatio']>=5 or Control['HiQualLimit']==0:
                    for event in report['Events']:
                        if not event['crFlag']:
                            corr.append({})
                            corr[cIdx]['importance'] = event['importance']
                            corr[cIdx]['day'] = event['day']
                            corr[cIdx]['peak'] = event['peakTime']
                            corr[cIdx]['count'] = 1
                            corr[cIdx]['userID']= obs.ID
                            corr[cIdx]['crFlag']=HIQUAL_CORRELATED
                            cIdx+=1
                            event['crFlag'] = HIQUAL_CORRELATED

    return (cIdx-Control['nCorr'])
#-------------------------------------------    
if __name__ == '__main__':
    import argparse

    #Establish the root directory for the analysis and the Observers and Stations files
    parser=argparse.ArgumentParser(description="Process SID reports and generate reports on correlations")
    parser.add_argument("-d", "--directory", help="Path to root directory for analysis (default: current directory)")
    parser.add_argument("-o", "--observer", help="Path to Observer information file (default: SIDAnalObservers.ini in current directory)")
    parser.add_argument("-s", "--station", help="Path to Station information file (default: SIDAnalStations.ini in current directory)")
    args = parser.parse_args()

    #Set the path based on command line argument or the current directory
    if args.directory:
        PATH = os.path.expanduser(args.directory)
    else:
        PATH = os.getcwd()

    #Check that the path exists
    if os.path.isdir(PATH):
        #Check path for read/write access
        if not (os.access(PATH, os.W_OK) and os.access(PATH, os.R_OK)):
            print "Check write/read access for {}".format(PATH)
            sys.exit()
    else:
        #Makes the necessary directories (more for testing)
        print "Creating path {}".format(PATH)
        if not os.path.exists(PATH):
            os.makedirs(PATH)

    #Update the control information dictionary
    Control_dict['path'] = PATH

    #Set the Observer and Station initialization files
    if args.observer:
        OBSERVERS_INI=os.path.expanduser(args.observer)
    if args.station:
        STATION_INI=os.path.expanduser(args.station)

    SID_reporter(OBSERVERS_INI,STATION_INI)

