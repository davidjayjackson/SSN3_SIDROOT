import os
import string
import sys
import glob

def cevents(OUT=None):
    
    eventFilePath,newFile=GetFilePath()
    qualCodes=GetEventQualifiers()
    if OUT==None:
        ProcessFiles(eventFilePath,newFile,qualCodes)
    else:
        ProcessFiles(eventFilePath,OUT,qualCodes)
        
def prompt_month_year():
    '''Returns the raw_input function with a request for date information. 
    Written as a function to facilitate unit testing'''
    return raw_input('\n Enter 3 character month and 2 digit year (any number of characters between them): \nExamples: Jun11, Jun 11, Jun...11: ')


def GetFilePath(input_func=prompt_month_year):

    #Get directory with input files.
    #Assume the directory has the name yyyymm (4 digit year, 2 digit month)---I think this is incorrect
    #Assume the directory is named eventlistings and its parent is mmm_yy, with mmm being three uppercase letters for the month, yy the 2 digit year
    #The event filenames will have the format yyyymmddevents.txt (4 digit year, 2 digit month, 2 digit day)
    #Generated files  will go to the directory mmm_yy/Data_Received
    #Output files will be  yyyymmXXX.txt, XXX being either FLA or XRA

    '''Not clear that entering yyyymmm is necessary. For now will have user enter mmm yy
    months={'01':'JAN','02':'FEB','03':'MAR','04':'APR','05':'MAY','06':'JUN','07':'JUL','08':'AUG','09':'SEP','10':'OCT','11':'NOV','12':'DEC'}
    yyyymm=raw_input('Enter the 4 digit year and the 2 digit month: ')

    if len(yyyymm)>=6:
        #Extract and test year
        yyyy=yyyymm[0:4]
        if not str.isdigit(yyyy):
            sys.exit("\n Invalid date: year field is not integer.\n")

        #Extract and test month.  Should this be a 2-digit month or a 2-character month?

        mm=yyyymm[-2:]
        if not str.isdigit(mm):
            sys.exit("\n Invalid date: month field is not an integer.\n")

        yyyymm=yyyy+mm
        mmm_yy=months[mm]+'_'+yyyy[2:]
    else:
        sys.exit('\n Invalid entry')'''

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
    mmm_yy = mmm + '_' + yy

    baseDir=os.path.expanduser(raw_input("What is the path to the directory {} [current directory]? ".format(mmm_yy)))
    if baseDir=='':
        baseDir=os.getcwd()
        
    eventFilePath=os.path.join(baseDir,mmm_yy)
    '''fns=[]
    dirs=glob.glob('eventFilePath/*/') #This commented out section is probably only necessary in Unix
    for dir in dirs:
        if os.path.split(dir)[1].lower()=='eventlisting/': 
            fns.append(dir)
    if len(fns)==1:
        eventFilePath=os.path.join(eventFilePath)
    else:
        sys.exit('Too many or no Eventlisting directories\n')
    '''     
    #Check the directory

    #Set up paths. 
    eventFilePath=os.path.join(eventFilePath,'eventlistings','*events.txt') #Not consistent with checking all capitalizations above
    newFile=os.path.join(baseDir,mmm_yy,'Data Received',mmm_yy)

    return eventFilePath,newFile

def input_qualifiers():
    return raw_input('\n\n\tOptions - (FLA,XRA) \n \tEnter Event Qualifiers separated by commas ')

def GetEventQualifiers(input_func=input_qualifiers):

    #This accepts an arbitrary comma-separated list and normalizes it to all caps
    list=input_func()
    list=list.upper().split(',')
    list=[f.strip() for f in list]

    #Makes sure something was entered
    if len(list)==0:
        sys.exit('No qualifiers\n ')

    #Check to see if XRA and/or FLA are in the arbitrary list and create useful list
    #Any other entries are ignored
    rlist=[]
    if 'FLA' in list:
        rlist.append('FLA')
    if 'XRA' in list:
        rlist.append('XRA')
        
    '''if len(list)!=list.count('FLA')+list.count('XRA'):
        sys.exit('Incorrect qualifier\n')'''

    return rlist

def ProcessFiles(eventFilePath, newFile,qualCodes):

    eventPath=os.path.split(eventFilePath)[0]
    for code in qualCodes:
        sortBuffer=[]
        files=glob.glob(eventFilePath)
        for file in files:
            new=CopyValidEvents(file,code)
            sortBuffer.extend(new)

        if files:
            with open(newFile+code+'.txt','w') as fhout:
                if len(sortBuffer):
                    cm='00'
                    sortBuffer.sort(key=lambda s: s[3:14])
                    for entry in sortBuffer:
                        if cm!='00' and cm!=entry[3:5]:
                            fhout.write('\n')
                        cm=entry[3:5]
                        fhout.write('{}\n'.format(entry))
                else:
                    fh.write('No valid events found\n')
                    
def CopyValidEvents(eventfile, code):

    sortBuffer=[]
    
    #How about
    fn=os.path.split(eventfile)[1]
    date=fn[4:6]+' '+fn[6:8]

    with open(eventfile,'r') as fhin:
        for eline in fhin:
            outputline=''
            if eline[43:46]==code:
                outputline='{}     '.format(date)
                outputline+=eline[11:17]+eline[17:24]+eline[27:34]+eline[43:48]+eline[58:65]
                sortBuffer.append(outputline)

    return sortBuffer

if __name__ == '__main__':
    import argparse

    #Take an optional filename for output
    parser=argparse.ArgumentParser(description="Event summary output for input into R")
    parser.add_argument("-o", "--outfile", help="Base filename for output")

    args = parser.parse_args()

    if args.outfile:
        OUTFILE = os.path.expanduser(args.outfile)
        cevents(OUTFILE)    
    else:
        cevents()
        
        
