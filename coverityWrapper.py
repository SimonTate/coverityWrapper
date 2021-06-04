import sys, getopt
import logging
import json
import re
import subprocess
from colorama import init
from colorama import Fore, Back, Style
init()


logging.basicConfig(filename='coverityWrapper.log',format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler())

class FastDesktopWrapper:
  
    
    def __init__(self,argv):
        self.buildFile=None
        self.generateConfig=False
        self.configFile=None
        self.idir="idir"
        self.suppresions={}
        self.outputFile=None
        self.enableQuality=True
        self.fileFilter=None
        self.limitResults=1000
        self.skipAnalysis=False
        self.skipBuild=False
        self.outputType="pretty"
        self.checkerFilter=None
        self.extendedOutput=True
        self.generatePragma=False
        self.fileCache={}
        self.context=3
        self.issueCount=0
        self.summary=False
        self.suggestAnnotations=False
        try:
            opts, args = getopt.getopt(sys.argv[1:], 'd:c:l:i:q', ['dir=',"configFile=","enableQuality","limitResults=","includeFiles=","skipAnalysis","skipBuild","summary","checker=","context=","output=","outputFile=","generatePragma","suggestAnnotations"])
        except getopt.GetoptError:
            self.usage()
            sys.exit(2)

        for opt, arg in opts:
            if opt in ('-h', '--help'):
                self.usage()
                sys.exit(2)
            elif opt in ('-d', '--dir'):
                self.idir = arg
            elif opt in ('-c', '--configFile'):
                self.configFile = arg
            elif opt in ('-q', '--quiet'):
                logging.disable(logging.DEBUG)
            elif opt in ('--enableQuality'):
                self.enableQuality=True
            elif opt in ('--l', '--limitResults'):
                self.limitResults=arg
            elif opt in ('-i', '--includeFiles'):
                self.fileFilter=arg
            elif opt in ('--skipAnalysis'):
                self.skipAnalysis=True
            elif opt in ('--skipBuild'):
                self.skipBuild=True
            elif opt in ('--summary'):
                self.summary = True
            elif opt in ('--checker'):
                self.checkerFilter=arg
            elif opt in ('--context'):
                self.context = int(arg)
            elif opt in ('--generatePragma'):
                self.generatePragma=True
            elif opt in ('--suggestAnnotations'):
                self.suggestAnnotations=True
            elif opt in ('--output'):
                self.outputType=arg
                if self.outputType not in ["pretty","html","emacs"]:
                    self.usage()
                    sys.exit(2)
                if self.outputType=="emacs":
                    logging.disable(logging.DEBUG)
            elif opt in ('--outputFile'):
                self.outputFile=arg

        self.fileArgs=args

    def usage(self):

        help = """
coverityWrapper.py:
This script wraps Coverity Build, Analyse and Format Errors.
NOTE: The cov-* tools must be in the path
Syntax: coverityWrapper.py <options> <build command>
where:
<build commnand> is the build command to build the appliation
<options>: 
--dir <dir>              : (Optional) Specify the intermediate directory used to store the Coverity information in
--config|-c <file>       : (Optional) Specify the Coding standard config file to use for analysis
--quiet|-q               : (Optional) Disable output of standard out for the build and analyse step, set automatically when using emacs output
--includeFiles|-i <file> : (Optional) Filter results on filename regex
--enableQuality          : (Optional) Enable quality checkers
--skipBuild              : (Optional) Skip the build phase
--skipAnalysis           : (Optional) Skip the analysis phase (also skips the build phase)
--summary                : (Optional) Presents single line of information per defect instead of code detail
--context <num of lines> : (Optional) limits the number of lines around events, defaults to 3, 0 to remove context
--checker <checker>      : (Optional) limits results based on checker regex. ONLY WORKS WITH JSON OUTPUT!!!!
--generatePragmas        : (Optional) (Experimental) Generates a file (stored next to the source file) containing the pragma required to suppress  issues
--output <output type>   : (Optional) Choose from emacs, pretty, json and html. 
--outputFile <file|dir>  : (Optional) Specify the output file or dir for json and html mode respectively. Defaults to "pretty"
"""
        print(help)

    def doBuild(self):
        # Call cov build
        command=["cov-build","--dir", self.idir]
        if self.configFile:
            command.append("--emit-complementary-info")
        command.extend(self.fileArgs)
        logging.debug("Build Args:" + str(command))
        try:
            process = subprocess.Popen(command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            for line in iter(process.stdout.readline, b''):
                logging.debug(line.decode(sys.stdout.encoding).rstrip())

        except subprocess.CalledProcessError as e:
            logging.debug("Non zero exit :"+str(e.output)+" "+str(e.returncode))


    def loadSuppressions(self):
        logging.debug("Loading suppressions")
    # Search for suppression files
        try:
            lineNo=0
            with open(".suppressions", encoding='utf-8') as file:
                fileContents = file.readlines()
                for line in fileContents:
                    lineNo=lineNo+1
                    if line.lstrip().startswith("#"):
                        logging.debug("Found comment line")
                        continue
                mergekey,user,comment=line.split(',')
                if mergekey in self.suppresions:
                    logging.warning("Duplicate mergekey {} in suppression file in line {}".format(mergekey,lineNo))
                else:
                    self.suppresions[mergekey]={ 'user': user, 'comment' : comment }

        except Exception as e:
            logging.info("No suppression file found")
            return



    def doAnalyze(self):

        command=["cov-analyze","-all","--enable-constraint-fpp","--aggressiveness-level","high","--dir",self.idir]
        if self.configFile:
            command.extend(["--coding-standard-config",self.configFile])
        if not self.enableQuality:
            command.append("--disable-default")
        try:
            process = subprocess.Popen(command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            for line in iter(process.stdout.readline, b''):
                logging.debug(line.decode(sys.stdout.encoding).rstrip())

        except subprocess.CalledProcessError as e:
            logging.error("Non zero exit :"+str(e.output)+" "+str(e.returncode))



    def doFormatErrors(self):

        self.loadSuppressions()
        command=["cov-format-errors","--dir",self.idir]
        if self.fileFilter:
            command.extend(["--include-files", self.fileFilter])

        if self.outputType=="pretty" or self.outputType=="json" :
            if not self.outputFile:
                self.outputFile="results.json"
            # Call cov-format-errors
            command.extend(["--json-output-v7",self.outputFile])
            try:
                result=subprocess.check_output(command,stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                logging.debug("Non zero exit :"+str(e.output)+" "+str(e.returncode))

            if self.outputType=="pretty" or self.generatePragma:
                self.processJson()

        elif self.outputType == "html":
            if not self.outputFile:
                self.outputFile = "html_output"
            print("Generating html format (this may take a while!)")
            command.extend(["--html-output",self.outputFile])
            try:
                result=subprocess.check_output(command,stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                logging.debug("Non zero exit :"+str(e.output)+" "+str(e.returncode))
        elif self.outputType == "emacs":

            command.append("--emacs-style")
            try:
                process = subprocess.Popen(command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                for line in iter(process.stdout.readline, b''):
                    print(line.decode(sys.stdout.encoding).rstrip())

            except subprocess.CalledProcessError as e:
                logging.error("Non zero exit :" + str(e.output) + " " + str(e.returncode))

        if self.issueCount==0:
            return 0

        return 1

    def processJson(self):

        with open(self.outputFile, encoding='utf-8') as file:
            self.jsonData = json.load(file)

        pragmaCache={}

        self.failed = False
        # Iterate through errors
        self.issueCount=0
        totalIssues=len(self.jsonData['issues'])
        for issue in self.jsonData['issues']:
            if issue['mergeKey'] in self.suppresions:

                logging.debug("Skipping issue {}: Suppressed by {} Comment:{}".format(issue['mergeKey'],self.suppresions[issue['mergeKey']]['user'],self.suppresions[issue['mergeKey']]['comment']))
                continue
            if self.checkerFilter:
                pattern = re.compile(self.checkerFilter)
                matched = pattern.search(issue['checkerName'])
                if not matched:
                    continue
            fileName=issue['mainEventFilePathname']
            lineNumber=issue['mainEventLineNumber']
         #   print("File:"+issue['strippedMainEventFilePathname'])
            eventData,maxLineNumber=self.generateIssueData(issue)
            if self.outputType=="pretty":
                self.printIssue(issue,eventData,maxLineNumber)

            if fileName not in pragmaCache:
                pragmaCache[fileName]={}

            if lineNumber not in pragmaCache[fileName]:
                pragmaCache[fileName][lineNumber]=[]

            pragmaCache[fileName][lineNumber].append(issue)
            self.issueCount=self.issueCount+1

        print("Found " + str(totalIssues) + " issues(before global suppression)")
        print("Found " + str(self.issueCount) + " issues(after global suppression)")

        if self.generatePragma:
            for file in pragmaCache:
                fileContents=None
                if not file in self.fileCache:
                    try:
                        with open(file, encoding='utf-8') as oldfile:
                            fileContents = oldfile.readlines()
                            self.fileCache[file] = fileContents
                    except Exception as e:
                        print("Exception" + str(e))

                    continue
                else:
                    fileContents = self.fileCache[file]

                count=1
                newContents=[]

                for line in fileContents:
                    if count in pragmaCache[file]:
                        for issue in pragmaCache[file][count]:
                            newContents.append('#pragma coverity compliance fp:1 "'+issue['checkerName']+'" "AUTOGENERATED: REQUIRES REVIEW"\n')
                    newContents.append(line)
                    count=count+1
                newFile=file+".pragmas"
                try:
                    with open(newFile, "w", encoding='utf-8') as newfile:
                        for line in newContents:
                            newfile.write(line)
                except Exception as e:
                    print("Couldn't write "+newFile+" exception:"+e)



    def generateIssueData(self,issue):
        fileName=issue['strippedMainEventFilePathname']
        eventCache={}
        maxLineNumber=0
        # Gather events for later display
        if self.extendedOutput and issue['events']:
            for event in issue['events']:
                eventFileName=event['filePathname']
                eventFileLine=event['lineNumber']
                eventFileIndex=eventFileLine-1
                fileContents=None

                if not eventFileName in self.fileCache:
                    try:
                        with open(eventFileName, encoding='utf-8') as file:
                            fileContents = file.readlines()
                            self.fileCache[eventFileName]=fileContents
                    except Exception as e:
                        print("Exception"+str(e))

                        continue
                else:
                    fileContents=self.fileCache[eventFileName]

                maxIndex=len(fileContents)

                if not fileContents:
                    continue

                if not eventFileName in eventCache:
                    eventCache[eventFileName]={ "lines" :{} }

                startIndex=eventFileIndex-self.context
                if startIndex<0:
                    startIndex=0
                endIndex=eventFileIndex+self.context+1 # Why because range is not inclusive
                if endIndex>maxIndex:
                    endIndex=maxIndex

                if endIndex+1>maxLineNumber:
                    maxLineNumber=endIndex+1

                for index in range(startIndex,endIndex):

                    lineNumber=index+1
                    if not lineNumber in eventCache[eventFileName]['lines']:
                        eventCache[eventFileName]['lines'][lineNumber]={ "contents" : fileContents[index] , "events" : [] }

                eventCache[eventFileName]['lines'][eventFileLine]['events'].append(event)
                eventCache[eventFileName]['maxLineNumber']=maxLineNumber

        return eventCache,maxLineNumber

    def printIssue(self,issue,eventData,maxLineNumber):
        defectString = "Found issue:" + issue['checkerName'] + " in File:" + issue[
            'strippedMainEventFilePathname'] + " at line " + str(issue['mainEventLineNumber']) + " - " + \
                        issue['checkerProperties']['subcategoryLongDescription']
        defectString = issue['mergeKey'] + ":" + issue['checkerName'] + ":" + issue['strippedMainEventFilePathname'] + ":" + str(issue['mainEventLineNumber']) + " - " + issue['checkerProperties']['subcategoryLongDescription']
        print(Fore.YELLOW+defectString)

        if self.summary:
            return

        #print("MaxNumberLength:" + str(len(str(maxLineNumber))))
        displayString=" %"+str(len(str(maxLineNumber)))+"d : %s"
        self.currentFileName=issue['mainEventFilePathname']

        for file in eventData:
            currentLine=1
            if self.currentFileName!=file:
                print(Fore.MAGENTA+"  "+file)
            self.currentFileName=file
            postPrint=[]
            for line in eventData[file]['lines']:
                if not currentLine==1 and line-currentLine>1:
                    print("---")
                for issue in eventData[file]['lines'][line]["events"]:
                    issueDisplayString=""
                    colour = Fore.WHITE
                    if issue['eventTag']=="path":
                        colour =Fore.GREEN
                    elif "example" in issue['eventTag'] :
                        colour = Fore.YELLOW
                    else:
                        colour = Fore.RED

                    issueDisplayString=issueDisplayString+colour+" %-" + str(len(str(maxLineNumber))) + "d  : %s"
                    if issue['main']:
                        issueDisplayString = issueDisplayString + "( To suppress use: \"// coverity["+issue['eventTag']+" : SUPPRESS]\" )"
                    issueString=issueDisplayString%(issue['eventNumber'],issue['eventDescription'])
                    if issue['eventTag']=="caretline":
                        postPrint.append(issueString)
                    else:
                        print(issueString)

                displayString = Fore.WHITE+"  %" + str(len(str(maxLineNumber))) + "d : %s"
                print(displayString % (line, eventData[file]['lines'][line]['contents'].rstrip()))

                currentLine=line
                if len(postPrint)>0:
                    for line in postPrint:
                        print(line)
    def run(self):

        if not self.skipAnalysis and not self.skipBuild:
            self.doBuild()
        if not self.skipAnalysis:
            self.doAnalyze()
        return self.doFormatErrors();

            
if __name__ == "__main__":
    wrapper=FastDesktopWrapper(sys.argv[1:])
    sys.exit(wrapper.run())
            
