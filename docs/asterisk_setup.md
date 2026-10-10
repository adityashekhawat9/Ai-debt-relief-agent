# Asterisk AudioSocket Configuration

To integrate the AI Voice Platform with Asterisk via AudioSocket, you need to ensure the `app_audiosocket.so` module is loaded and configure the extensions and manager.

## 1. Load AudioSocket Module
Ensure that `app_audiosocket.so` is built and loaded in your Asterisk instance. Check `modules.conf`:
```ini
load => app_audiosocket.so
```

## 2. extensions.conf
Snippet for the AI outbound dialplan:
```ini
[ai-outbound]
exten => s,1,NoOp(AI Voice Platform outbound call)
 same => n,Answer()
 same => n,Set(CALL_ID=${CALL_ID})
 same => n,Set(LEAD_ID=${LEAD_ID})  
 same => n,AudioSocket(ai-voice-platform,9092)
 same => n,Hangup()
```

## 3. manager.conf
AMI credentials for the telephony service:
```ini
[aicalls]
secret = changeme
deny = 0.0.0.0/0.0.0.0
permit = 172.20.0.0/255.255.0.0
read = system,call,log,verbose,agent,user,config,dtmf,reporting,cdr,dialplan
write = system,call,agent,user,config,command,reporting,originate
writetimeout = 5000
```

## 4. PJSIP Trunk (Stub)
Make sure your PJSIP endpoints are properly configured to route calls.
```ini
[mytrunk]
type=endpoint
transport=transport-udp
context=ai-outbound
disallow=all
allow=ulaw
```
