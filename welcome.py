#!/usr/bin/env python3
import requests
import json
import urllib.request
from datetime import datetime
import textwrap
import time
import snap7

with open("welcome.json", "r") as f:
    s = json.load(f)

headers = {"Authorization": f"Bearer {s['API_KEY']}", "Content-Type": "application/json"}

def wait_for_arrive_or_leave():
    last_absence = time.time()
    prev_presence = 1
    while(True):
        try:
            with urllib.request.urlopen("http://" + s["jDaLog"] + "/in.json") as r:
                lst = json.loads(r.read())
        except urllib.error.URLError as e:
            time.sleep(10)
            continue
        presence = lst["2B_pg"]["value"]
        mhall = lst["2B_bh"]["value"]
        if prev_presence == 0 and presence == 1:
            return "arrive"
        prev_presence = presence
        if mhall and time.time() - last_absence > 300:
            return "leave"
        if not presence:
            last_absence = time.time()
        time.sleep(0.5)

def last_change(i):
    with urllib.request.urlopen("http://" + s["jDaLog"] + f"/in/{i}/json/week.json") as r:
        recs = json.loads(r.read())
    lastchange = 0
    lastvalue = 0
    for key, value in recs[f"{i}"].items():
        if value != lastvalue:
            lastchange = key
            lastvalue = value
    age = time.time() - float(lastchange)
    return age    

def last_away_duration(i):
    with urllib.request.urlopen("http://" + s["jDaLog"] + f"/in/{i}/json/week.json") as r:
        recs = json.loads(r.read())
    lastleave = 0
    lastreturn = 0
    laststate = 0
    for key, value in recs[f"{i}"].items():
        if value == 0 and laststate == 1:
            lastleave = key
        if value == 1 and laststate == 0:
            lastreturn = key
        laststate = value
    if float(lastleave) > float(lastreturn):
        return time.time() - float(lastleave)
    return float(lastreturn) - float(lastleave)

def text(blok):
    if isinstance(blok, list):
        return "\n".join(blok)
    return blok

def add_sensor(lst, s):
    rv = ""
    if lst[s]["valid"]:
        d = lst[s].get("decimals")
        rv += lst[s]["name"] + " " + f"{float(lst[s]['value']):.{d}f}"
        if "unit" in lst[s]:
            rv += " " + lst[s]["unit"]
    else:
        rv += lst[s]["name"] + " OFFLINE"
    return rv + "\n"

def meas_block():
    return ""
    with urllib.request.urlopen("http://" + s["jDaLog"] + "/in.json") as r:
        lst = json.loads(r.read().decode("ascii", "replace"))
    lst["soc"] = {}
    lst["soc"]["valid"] = lst["mt1_1_soc"]["valid"] and lst["mt2_1_soc"]["valid"] and lst["mt3_1_soc"]["valid"]
    lst["soc"]["name"] = "Battery SOC"
    lst["soc"]["unit"] = "%"
    lst["soc"]["value"] = (lst["mt1_1_soc"]["value"] + lst["mt2_1_soc"]["value"] + lst["mt3_1_soc"]["value"]) / 3

    rv  = add_sensor(lst, "2B_bt")
    rv += add_sensor(lst, "2B_tl")
    rv += add_sensor(lst, "2B_ts")
    rv += add_sensor(lst, "2B_tss")
    rv += add_sensor(lst, "ct003_pd")
    rv += add_sensor(lst, "soc")
    rv += add_sensor(lst, "solarlog_pdc")
    rv += add_sensor(lst, "2B_tsl")
    rv += add_sensor(lst, "host_uptime")
    rv += add_sensor(lst, "2B_kmt")
    rv += f"Last time that a scoop of coal was put in the stove was {last_change('2B_sfc'):.0f} seconds ago.\n"
    rv += f"The last time that master took a shower is {last_away_duration('2B_sh'):.0f} seconds ago.\n"
    return rv

def return_block():
    return f"The master was away for {last_away_duration('2B_pg'):.0f} seconds.\n"
    
#print(prompt)

VERTALING = {
    "\u2014": "-", "\u2013": "-",      # em-dash, en-dash
    "\u2018": "'", "\u2019": "'",      # curly quotes
    "\u201c": '"', "\u201d": '"',
    "\u00a0": " ",                      # non-breaking space
}

p = open(s["printer"], 'wb')
now = datetime.now()
timestr = now.strftime("%a %d %b %Y %H:%M")
#p.write(("Started welcome script, " + timestr + "\n\n\n\n\n\n").encode("ascii"))
client = snap7.client.Client()
pol = "init"

while True:
    
    with open("welcome.json", "r") as f:
        s = json.load(f)
        
    #client.connect(s["plc"], 0, 1)
    for attempt in range(3):
        try: 
            client.connect(s["plc"], 0, 1)
            break
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(2)
    data = client.db_write(s["plc_db"], 2, b'x')
    client.disconnect()    


    sys = text(s["prompt_interface"]) + "\n\n"
    if pol == "init":
        sys += text(s["prompt_init"]) + "\n\n"
    if pol == "arrive":
        sys += text(s["prompt_returnhome"]) + "\n\n"
    if pol == "leave":
        sys += text(s["prompt_leavehome"]) + "\n\n"
    sys += text(s["prompt_about"]) + "\n\n"
    #prompt += "Historic messages, to avoid repeating yourself. These are responses TO BE AVOIDED:\n"
    #for m in s["history"]:
    #    prompt += m + "\n\n"
    #prompt += "End of historic messages. DO NOT REPEAT THESE!\n\n"
    sys += text(s["prompt_measurement"]) + "\n"

    meas = meas_block()
    #prompt += meas_block()
    now = datetime.now()
    if pol == "arrive":
        meas += return_block()
    meas += now.strftime("\n\nCurrent date/time: %a %d %b %Y %H:%M\n\n")

    history = []
    history.append({"role":"system", "content": sys})
    #for h in s["history"]:
    #    history.append({"role":"user", "content": h["user"]})
    #    history.append({"role":"assistant", "content": h["assistant"]})
    history.append({"role": "user", "content": meas})

    payload = {
        "model": s["MODEL"],
        "messages": history,
        "stream": False,
        "tools":[{"type":"connector", "connector_id":"jdalink_2360"}]
    }
    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers=headers,
        json=payload
    ).json()
    print(response)
    
    #if "messages" in response["choices"][0]:
    #    reply = "\n".join(m.get("content") or "" for m in response["choices"][0]["messages"] if m.get("content") )
    #else:
    #    reply = response["choices"][0]["message"]["content"]
        
    def get_text(msg):
        c = msg.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):           # content-parts (tool-berichten)
            return "\n".join(p.get("text", "") for p in c if p.get("type") == "text")
        return ""

    reply = "\n".join(
        get_text(m)
        for m in response["choices"][0]["messages"]
        if m.get("role") == "assistant" and get_text(m)
    )    
        
    timestr = now.strftime("%a %d %b %Y %H:%M")
    history.append({"role": "assistant", "content": reply})
    s["history"].append({"user":meas, "assistant":reply})
    reply = reply.replace("\n", "\r\n")
    print(timestr)
    print(meas)
    print(reply)
        #p.write((reply + "\r\n\n\n").encode("ascii"))
    for oud, nieuw in VERTALING.items():
        reply = reply.replace(oud, nieuw)

    p.write((timestr + "\n").encode("ascii"))
    lines = textwrap.wrap(reply, width=80, break_long_words=False, break_on_hyphens=False)
    for line in lines:
        p.write((line[:80] + "\n").encode("ascii", "replace"))
    p.write(("\n\n\n\n\n").encode("ascii", "replace"))
    p.flush()

    s["history"] = s["history"][-25:]

    with open("welcome.json", "w") as f:
        json.dump(s, f, indent=2)

    pol = wait_for_arrive_or_leave()
