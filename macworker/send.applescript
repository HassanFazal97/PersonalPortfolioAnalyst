-- Send an iMessage. Usage: osascript send.applescript "<body>" "<recipient>"
on run argv
    set msgBody to item 1 of argv
    set targetBuddy to item 2 of argv
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetParticipant to participant targetBuddy of targetService
        send msgBody to targetParticipant
    end tell
end run
