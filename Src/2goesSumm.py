import os
import string
import sys
import glob


def Eventsumm(OUT=None):

    eventFilePath,newFile,date=GetFilePath()
    if OUT==None:
        ProcessFiles(eventFilePath,newFile,date)
    else:
        ProcessFiles(eventFilePath,OUT,date)

def prompt_month_year():
    '''Returns the raw_input function with a request for date information. 
    Written as a function to facilitate unit testing'''
    return raw_input('\n Enter 3 character month and 2 digit year (any number of characters between them): \nExamples: Jun11, Jun 11, Jun...11: ')

def GetFilePath(input_func=prompt_month_year):

    '''#Get directory with input files.
    #Assume the directory is named eventlistings and its parent is mmm_yy, with mmm being three uppercase letters for the month, yy the 2 digit year
    #The event filenames will have the format yyyymmddevents.txt (4 digit year, 2 digit month, 2 digit day)
    #Generated files  will go to the directory mmm_yy/Data_Received
    #Output files should be renamed to  yyyymmXXXSumm2.txt, XXX being either FLA or XRA'''

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

    #Set up paths. 
    eventFilePath=os.path.join(baseDir,mmm_yy,'Data Received',mmm_yy+'XRA.txt')
    newFile=os.path.join(baseDir,mmm_yy,'Data Received',mmm_yy+'XRASumm2.csv')

    return eventFilePath,newFile,mmm_yy

def ProcessFiles(eventFilePath, newFile,date):

    month=[0 for f in range(0,31)]
    classes={'A':month[:],'B':month[:],'C':month[:],'M':month[:],'X':month[:]}
    
    with open(eventFilePath, 'r') as fh:
        for line in fh:
            if line=='\n':
                continue
            day=int(line[3:5])
            if day==0:
                continue

            flareclass=line[35:36]
            if not flareclass in classes:
                classes[flareclass]=month[:] 
            classes[flareclass][day-1]+=1

    types=classes.keys()
    types.sort()

    with open(newFile,'w') as fh:
        #fh.write("SEC Event List Summary\n  {} \n  Event Type: XRA \n\n".format(date))
        #fh.write("Day:     ")
        #fh.write(''.join('{:2},  '.format(f) for f in range(1,day+1))+'\n')

        for t in types:
            fh.write(t+'-Class, ')
            s=''.join('{:2}, '.format(f) for f in classes[t][:day])
            fh.write(s.rstrip()[:-1]+'\n')

if __name__=='__main__':
    import argparse

    #Take an optional filename for output
    parser=argparse.ArgumentParser(description="Event summary output for input into R")
    parser.add_argument("-o", "--outfile", help="File for output")

    args = parser.parse_args()

    if args.outfile:
        OUTFILE = os.path.expanduser(args.outfile)
        Eventsumm(OUTFILE)    
    else:
        Eventsumm()
