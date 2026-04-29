#Requires AutoHotkey v2.0
; NetPhone Auto-Caller (Version 10 - Final)
; Steuert den Browser per Mausklick für maximale Zuverlässigkeit.

; =====================================================================
;                  1. EINSTELLUNGEN
; =====================================================================

RING_TIMEOUT_S          := 15  ; Klingelzeit in Sekunden, bis automatisch aufgelegt wird.
POST_CALL_DELAY_MS      := 1200 ; Kurze Pause nach Gesprächsende für Notizen etc.

; ===== Experten-Einstellungen (normalerweise nicht ändern) =====
BROWSER_EXE             := "chrome.exe"
BROWSER_TITLE_MATCH     := "Auto-Caller" ; So muss der Tab-Titel in Chrome beginnen.

; ===== Erkennung NetPhone (basiert auf Ihren Screenshots) =====
RING_RE    := "i)(Gehender Ruf|Klingeln|Verbinden mit|Ringing|Ruf)"
CONN_RE    := "i)(Verbindung aufgebaut|Verbunden|Gespräch aktiv)"
MAILBOX_RE := "i)(Mailbox|Anrufbeantworter|Voicemail)"


; =====================================================================
;                  2. KALIBRIERUNGS-HOTKEYS
; =====================================================================
; Führen Sie die Kalibrierung einmal durch, nachdem Sie das Skript gestartet haben.

; -> Maus über den "Pause"-Button (⏸) im Auto-Caller-Fenster bewegen und diese Tastenkombination drücken
^!1:: SaveButtonPos("pause_resume")

; -> Maus über den "Weiter"-Button (⏭) im Auto-Caller-Fenster bewegen und diese Tastenkombination drücken
^!2:: SaveButtonPos("next")

; -> Skript beenden
^!q:: ExitApp()


; =====================================================================
;                  AB HIER BEGINNT DIE AUTOMATIK
; =====================================================================

; ===== Globale Variablen (nicht ändern) =====
global g_prevState     := "idle"
global g_callConnected := false
global g_timerRunning  := false
global g_lastStateTip  := ""

; ===== Skriptstart =====
TrayTip("Auto-Caller Skript", "Gestartet. Bitte jetzt kalibrieren!", 10)
SetTimer(CheckNetPhone, 300)
return


; =====================================================================
;                    H A U P T L O G I K
; =====================================================================
CheckNetPhone() {
    global g_prevState, g_callConnected, g_timerRunning
    static startTick := 0

    hwnd := FindNetPhoneWin()
    if !hwnd {
        ShowStateTip("NetPhone nicht gefunden")
        g_prevState     := "idle"
        g_timerRunning  := false
        return
    }

    state := ReadNPState(hwnd)
    ShowStateTip(state)

    ; --- Fall 1: Anruf wurde beendet (Wechsel zu "idle") ---
    if (state == "idle" && g_prevState != "idle") {
        prev := g_prevState
        g_prevState     := "idle"
        g_callConnected := false
        g_timerRunning  := false
        ResumeAfterHangup(prev)
        return
    }

    ; --- Fall 2: Anruf wurde verbunden ---
    if (state == "connected") {
        g_prevState     := "connected"
        g_callConnected := true
        g_timerRunning  := false
        PauseInBrowser()
        return
    }

    ; --- Fall 3: Es klingelt (Timeout-Logik) ---
    if (state == "ringing") {
        g_prevState := "ringing"
        if !g_timerRunning {
            g_timerRunning  := true
            g_callConnected := false
            startTick       := A_TickCount
        }

        elapsed := (A_TickCount - startTick) / 1000.0
        if (elapsed >= RING_TIMEOUT_S) {
            TrayTip("Timeout", "Klingelzeit abgelaufen. Lege auf.", 10)
            g_timerRunning := false
            g_prevState    := "idle"
            HangupActiveCall(hwnd)
            Sleep(400)
            NextInBrowser()
        }
        return
    }

    g_prevState := state
}


; =====================================================================
;                  A K T I O N E N
; =====================================================================
ResumeAfterHangup(prevState) {
    Sleep(POST_CALL_DELAY_MS)
    if (prevState == "connected") {
        ; Fall A: Wir waren verbunden, also war der Caller pausiert.
        ; -> Erst fortsetzen (Klick auf Pause/Resume), dann zum nächsten (Klick auf Weiter).
        ResumeInBrowser()
        Sleep(300)
        NextInBrowser()
    } else {
        ; Fall B: Es hat nur geklingelt (Timeout).
        ; -> Direkt zum nächsten (Klick auf Weiter).
        NextInBrowser()
    }
}

PauseInBrowser() {
    if (win := EnsureAutoCallerWin())
        ClickButton(win, "pause_resume")
}

ResumeInBrowser() {
    if (win := EnsureAutoCallerWin())
        ClickButton(win, "pause_resume")
}

NextInBrowser() {
    if (win := EnsureAutoCallerWin())
        ClickButton(win, "next")
}


; =====================================================================
;                  H I L F S F U N K T I O N E N
; =====================================================================
FindNetPhoneWin() {
    return WinExist("ahk_exe NetPhone Client.exe")
}

ReadNPState(hwnd) {
    text := WinGetText("ahk_id " hwnd)
    if InStr(text, "Mailbox") || InStr(text, "Anrufbeantworter")
        return "mailbox"
    if RegExMatch(text, CONN_RE)
        return "connected"
    if RegExMatch(text, RING_RE)
        return "ringing"
    return "idle"
}

HangupActiveCall(hwnd) {
    WinActivate("ahk_id " hwnd)
    WinWaitActive("ahk_id " hwnd, , 1)
    Send("{Esc}")
    Sleep(250)
    if (ReadNPState(hwnd) == "ringing")
        Send("{Alt}{Right 3}a{Enter}")
}

EnsureAutoCallerWin() {
    win := WinExist(BROWSER_TITLE_MATCH " ahk_exe " BROWSER_EXE)
    if !win {
        TrayTip("Fehler", "Auto-Caller Tab nicht gefunden!", 10)
        return 0
    }
    WinActivate("ahk_id " win)
    if !WinWaitActive("ahk_id " win, , 2) {
        TrayTip("Fehler", "Konnte Auto-Caller Tab nicht aktivieren!", 10)
        return 0
    }
    Sleep(250)
    return win
}

ClickButton(win, which) {
    iniFile := A_ScriptDir "\LeadCaller_Coords.ini"
    x := IniRead(iniFile, "ButtonCoords", which "_x", "FAIL")
    y := IniRead(iniFile, "ButtonCoords", which "_y", "FAIL")

    if (x = "FAIL" || y = "FAIL") {
        TrayTip("Kalibrierung fehlt!", "Bitte Maus über '" . which . "'-Button halten und Hotkey drücken.", 10)
        return
    }

    TrayTip("Aktion", "Klicke auf Button: " . which, 3)
    WinGetPos(&winX, &winY, ,, "ahk_id " win)
    CoordMode("Mouse", "Screen")
    MouseGetPos(&origX, &origY)
    Click(winX + x, winY + y)
    MouseMove(origX, origY, 0)
}

SaveButtonPos(which) {
    if !(win := EnsureAutoCallerWin())
        return

    CoordMode("Mouse", "Screen")
    MouseGetPos(&mX, &mY)
    WinGetPos(&winX, &winY, ,, "ahk_id " win)
    relX := mX - winX
    relY := mY - winY

    iniFile := A_ScriptDir "\LeadCaller_Coords.ini"
    IniWrite(relX, iniFile, "ButtonCoords", which "_x")
    IniWrite(relY, iniFile, "ButtonCoords", which "_y")

    SoundBeep(1200, 150)
    TrayTip("Kalibrierung", "'" . which . "' Position gespeichert!", 5)
}

ShowStateTip(state) {
    global g_lastStateTip
    if (state != g_lastStateTip) {
        TrayTip("NetPhone Zustand", state, 2)
        g_lastStateTip := state
    }
}
