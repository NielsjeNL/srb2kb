# import funny stuff
from flask import Flask, jsonify, render_template
import srb2kpacket
import requests
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import concurrent.futures
from datetime import datetime
import argparse

#### TODOS
# TODO: when sorting by name, unreachable servers pop up first
# TODO: addon list is very long with 115 addon servers. should make it so the list is just as long as the players table and/or set a minimum height

#### FEATURE REQUESTS
# FR: sort by region. serverWhois has continent information, use that?
# FR: filter servers by addons. 
# Ashnal - Today at 2:25 PM
# maybe like a little filter box that filters the list by whther the server has an addon containing the string you type or not
# FR: sort table by kartspeed/gamemode

# parse commandline arguments
if __name__ == "__main__":
    # ARGUMENTS
    # Use argparse to parse arguments
    parser = argparse.ArgumentParser(prog="srb2kb", description="Unofficial SRB2Kart Server Browser")
    parser.add_argument("-p", "--port", type=int, default="80", help="Port to serve webpages on (default: 80)")
    parser.add_argument("-v", "--verbose", type=bool, default=False, help="Show verbose output")

    parsedArgs = parser.parse_args()

# variables
app = Flask(__name__)
allServerInfo = []
allServerInfoStore = []
allServerFlags = {}
curDateTime = ""
serverCounter = 1

# --- flask webapp ---
# include some other routes to prevent link rot/be more flexible/insert dumb reason
@app.route('/', methods=["GET"])
@app.route('/browser/', methods=["GET"])
@app.route('/browser/index.html', methods=["GET"])
def srb2kart_browser():

    # make sure we have data
    # otherwise import some empty data
    if len(allServerInfo) == 0:
        serverInfo = {  
                        'servername': 'EMPTY',
                        'gametype': 'EMPTY',
                        'players': {
                            'count': 0,
                            'max': 0
                            },
                        'ip': 'EMPTY',
                        'port': '5029'
                        }
        allServerInfo.append(serverInfo)
    # TODO: also add allServerFlags info
    
    # serve the page
    return render_template('index.html', allServerInfo=enumerate(allServerInfo), allServerFlags=allServerFlags, curDateTime=curDateTime)

# --- kart server related functions ---
def updateServers():
    """"Update the allServerInfo list with data from all kart servers. List of kart servers retrieved from the default master server."""
    # first get a list of all servers from the master server
    try:
        print("Getting list of servers from https://ms.kartkrew.org/ms/api/games/SRB2Kart/7/servers?v=2")
        msData = requests.get("https://ms.kartkrew.org/ms/api/games/SRB2Kart/7/servers?v=2")
    except:
        print("Could not get master server data. Not updating server information.")
        return
    
    # format it and get list of servers with IP, port and contact info
    msDataServers = msData.text.split("\n")

    # use global vars and clear them (to remove old entries)
    global allServerInfo
    global allServerInfoStore
    global curDateTime
    global serverCounter

    allServerInfoStore = []
    serverCounter = 1

    # create list of servers to check
    serversToCheck = []

    # extract ip's and ports
    for line in msDataServers:
        # 0 length line is given as last line so need to catch it
        if len(line) == 0:
            if parsedArgs.verbose: print("Reached end of MS server list or got an empty line.")
            break

        line = line.split(" ")
        serversToCheck.append([line[0], line[1]])

    # call threads to check servers
    print("Checking all servers...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []

        for key, value in serversToCheck:
            futures.append(executor.submit(appendServerInfo, ip=key, port=value))
    print("Checks done.")

    # sort list on amount of players and amount of max players
    allServerInfoStore.sort(key=lambda x: (x['players']['count'],x['players']['max']), reverse=True)

    # Store current date and time
    curDateTime = datetime.now().strftime("%d/%m/%Y %H:%M:%S CET")

    # replace the old info with the new info
    allServerInfo = allServerInfoStore

def appendServerInfo(ip='10.0.0.26', port='5029'):
    """This function retrieves server information and appends it to the allServerInfoStore list. It also retrieves geo IP information for the requested IP."""
    # first declare global variables
    global allServerInfoStore
    global allServerFlags
    global serverCounter

    # try filling a server's info
    try:
        # hey hello what's up?
        serverInfo = srb2kpacket.SRB2K().Main(ip, int(port))
        
        if parsedArgs.verbose: print(str("|{:<26}|{:<64}|").format(f" {ip}:{port}     ", f" OK: {serverInfo['players']['count']}/{serverInfo['players']['max']} on {serverInfo['level']['name']}"))
        
        # include IP and port in the info, or am i blind
        serverInfo['ip'] = ip
        serverInfo['port'] = port

        # add this server's info to the list
        allServerInfoStore.append(serverInfo)

    # XD
    except:
        if parsedArgs.verbose: print(str("|{:<26}|{:<64}|").format(str(f" {ip}:{port}"), " NOT REACHABLE"))
        
        serverInfo = {  
                    'servername': '<img src="https://srb2kart.aqua.fyi/images/picardydown.png" alt="Unreachable server" style="width: 24px; height: 18px;" /> Could not connect',
                    'gametype': '-',
                    'players': {
                        'count': 0,
                        'max': 0
                        },
                    'kartspeed': 'None',
                    'ip': ip,
                    'port': port,
                    'level': {
                        'title': 'EMPTY LAND ZONE'
                        }
                    }
        
        # append server info. oh wait, it's all empty
        allServerInfoStore.append(serverInfo)

    # if we have not WHOIS'd an IP before, get info
    # this does external calls to ipwhois.app. keep their rate limits in mind.
    if ip not in allServerFlags:
            if parsedArgs.verbose: print(str("|{:<26}|{:<64}|").format(str(f" {ip}:{port}"), " Server WHOIS info not cached, requesting it"))

            # try receiving info about the server from ipwhois.app
            try:
                # DISABLE FIRST LINE WHILE DEBUGGING OR GET RATE LIMITED
                serverWhois = requests.get('http://ipwhois.app/json/'+ip).json()
                #serverWhois = {'country': None, 'country_code': None, 'country_flag': "https://srb2kart.aqua.fyi/images/picardybad.png"}
                allServerFlags[ip] = [serverWhois['country'], serverWhois['country_code'], serverWhois['country_flag']] # TODO: could just pass the serverWhois block and use necessary info in the jinja template
            
            # if we can't reach them, fill the info with unknown stuff.
            # TODO: add a mechanic to retry connection after some time.
            except:
                if parsedArgs.verbose: print(str("|{:<26}|{:<64}|").format(str(f" {ip}:{port}"), " Could not get WHOIS info, using dummy thicc info"))
                allServerFlags[ip] = ['Unknown', 'XX', 'https://srb2kart.aqua.fyi/images/picardybad.png']
    
    # up the counter baybeee
    serverCounter += 1

# --- end of functions ---

# first we're scheduling the server update to run
scheduler = BackgroundScheduler()
scheduler.add_job(func=updateServers, trigger="interval", seconds=30)
scheduler.start()

# register exit tasks for when the script stops
# BUG: this sometimes causes my terminal to become unresponsive when ctrl+c'ing. might be a bug with the treading done in updateServers()
atexit.register(lambda: scheduler.shutdown())

# show script info
print(r"""
  ____      ____       ____    ____      _  __     ____   
 / __"| uU |  _"\ u U | __")u |___"\    |"|/ /  U | __")u 
<\___ \/  \| |_) |/  \|  _ \/ U __) |   | ' /    \|  _ \/ 
 u___) |   |  _ <     | |_) | \/ __/ \U/| . \\u   | |_) | 
 |____/>>  |_| \_\    |____/  |_____|u  |_|\_\    |____/  
  )(  (__) //   \\_  _|| \\_  <<  //  ,-,>> \\,-._|| \\_  
 (__)     (__)  (__)(__) (__)(__)(__)  \.)   (_/(__) (__) 
 
 ######
 # Script created by AquaMonkey#1470 and goulart#3978
 # https://github.com/NielsjeNL/SRB2KB
 ######""")

if parsedArgs.verbose == False:
    print("NOTE: Verbose information disabled. Individual server checks won't be shown. Enable with -v as argument.\n")

# update servers ourself for a first time so we can display at least SOMETHING
updateServers()

# start running the flask server
# flask is being run as a development server like this. works fine for our purposes though
app.run(host='0.0.0.0', port=parsedArgs.port)