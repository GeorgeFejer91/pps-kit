//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"sync"
	"syscall"
	"unsafe"
)

const (
	wmClose        = 0x0010
	wmCommand      = 0x0111
	wmAppProgress  = 0x8001
	wmAppDone      = 0x8002
	swShow         = 5
	wsOverlapped   = 0x00000000
	wsCaption      = 0x00C00000
	wsSysMenu      = 0x00080000
	wsMinimizeBox  = 0x00020000
	wsVisible      = 0x10000000
	wsChild        = 0x40000000
	bsPushButton   = 0x00000000
	ssLeft         = 0x00000000
	pbmSetRange32  = 0x0406
	pbmSetPos      = 0x0402
	idLaunchButton = 1001
	idCloseButton  = 1002
	errClassExists = 1410
)

var (
	user32              = syscall.NewLazyDLL("user32.dll")
	kernel32            = syscall.NewLazyDLL("kernel32.dll")
	comctl32            = syscall.NewLazyDLL("comctl32.dll")
	procCreateWindowEx  = user32.NewProc("CreateWindowExW")
	procDefWindowProc   = user32.NewProc("DefWindowProcW")
	procDestroyWindow   = user32.NewProc("DestroyWindow")
	procDispatchMessage = user32.NewProc("DispatchMessageW")
	procGetMessage      = user32.NewProc("GetMessageW")
	procGetModuleHandle = kernel32.NewProc("GetModuleHandleW")
	procLoadCursor      = user32.NewProc("LoadCursorW")
	procPostMessage     = user32.NewProc("PostMessageW")
	procRegisterClassEx = user32.NewProc("RegisterClassExW")
	procSendMessage     = user32.NewProc("SendMessageW")
	procSetWindowText   = user32.NewProc("SetWindowTextW")
	procShowWindow      = user32.NewProc("ShowWindow")
	procTranslateMsg    = user32.NewProc("TranslateMessage")
	procUpdateWindow    = user32.NewProc("UpdateWindow")
	procEnableWindow    = user32.NewProc("EnableWindow")
	procInitCommonCtrls = comctl32.NewProc("InitCommonControls")
)

type wndClassEx struct {
	Size       uint32
	Style      uint32
	WndProc    uintptr
	ClsExtra   int32
	WndExtra   int32
	Instance   syscall.Handle
	Icon       syscall.Handle
	Cursor     syscall.Handle
	Background syscall.Handle
	MenuName   *uint16
	ClassName  *uint16
	IconSm     syscall.Handle
}

type point struct {
	X int32
	Y int32
}

type msg struct {
	HWnd    syscall.Handle
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      point
}

type uiState struct {
	options      InstallOptions
	hwnd         syscall.Handle
	status       syscall.Handle
	progress     syscall.Handle
	percent      syscall.Handle
	launchButton syscall.Handle
	closeButton  syscall.Handle
	mutex        sync.Mutex
	latest       ProgressEvent
	result       InstallResult
	err          error
}

var activeUI *uiState

func shouldUseInteractiveUI() bool {
	return true
}

func runInteractive(ctx context.Context, options InstallOptions) int {
	procInitCommonCtrls.Call()
	state := &uiState{options: options}
	activeUI = state
	if err := registerWindowClass(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	className := utf16Ptr("PPSDownloaderWindow")
	title := utf16Ptr("PPS Toolkit Downloader")
	hwnd, _, err := procCreateWindowEx.Call(
		0,
		uintptr(unsafe.Pointer(className)),
		uintptr(unsafe.Pointer(title)),
		wsOverlapped|wsCaption|wsSysMenu|wsMinimizeBox,
		0x80000000,
		0x80000000,
		560,
		260,
		0,
		0,
		0,
		0,
	)
	if hwnd == 0 {
		fmt.Fprintln(os.Stderr, "create downloader window:", err)
		return 1
	}
	state.hwnd = syscall.Handle(hwnd)
	procShowWindow.Call(hwnd, swShow)
	procUpdateWindow.Call(hwnd)
	go func() {
		result, installErr := InstallFromManifest(ctx, options, state.report)
		state.mutex.Lock()
		state.result = result
		state.err = installErr
		state.mutex.Unlock()
		procPostMessage.Call(uintptr(state.hwnd), wmAppDone, 0, 0)
	}()
	var message msg
	for {
		ret, _, _ := procGetMessage.Call(uintptr(unsafe.Pointer(&message)), 0, 0, 0)
		if int32(ret) <= 0 {
			break
		}
		procTranslateMsg.Call(uintptr(unsafe.Pointer(&message)))
		procDispatchMessage.Call(uintptr(unsafe.Pointer(&message)))
	}
	state.mutex.Lock()
	defer state.mutex.Unlock()
	if state.err != nil {
		return 1
	}
	return 0
}

func registerWindowClass() error {
	className := utf16Ptr("PPSDownloaderWindow")
	instance, _, _ := procGetModuleHandle.Call(0)
	cursor, _, _ := procLoadCursor.Call(0, 32512)
	wc := wndClassEx{
		Size:       uint32(unsafe.Sizeof(wndClassEx{})),
		WndProc:    syscall.NewCallback(windowProc),
		Instance:   syscall.Handle(instance),
		Cursor:     syscall.Handle(cursor),
		Background: 6,
		ClassName:  className,
	}
	atom, _, err := procRegisterClassEx.Call(uintptr(unsafe.Pointer(&wc)))
	if atom == 0 && err != syscall.Errno(errClassExists) {
		return err
	}
	return nil
}

func windowProc(hwnd syscall.Handle, message uint32, wParam uintptr, lParam uintptr) uintptr {
	state := activeUI
	switch message {
	case 0x0001:
		if state != nil {
			state.createControls(hwnd)
		}
		return 0
	case wmAppProgress:
		if state != nil {
			state.refreshProgress()
		}
		return 0
	case wmAppDone:
		if state != nil {
			state.refreshDone()
		}
		return 0
	case wmCommand:
		id := wParam & 0xffff
		if id == idLaunchButton && state != nil {
			_ = launchEntrypoint(state.result.LaunchPath)
		}
		if id == idCloseButton {
			procDestroyWindow.Call(uintptr(hwnd))
		}
		return 0
	case wmClose:
		procDestroyWindow.Call(uintptr(hwnd))
		return 0
	case 0x0002:
		user32.NewProc("PostQuitMessage").Call(0)
		return 0
	}
	result, _, _ := procDefWindowProc.Call(uintptr(hwnd), uintptr(message), wParam, lParam)
	return result
}

func (u *uiState) createControls(hwnd syscall.Handle) {
	u.status = createChild("STATIC", "Preparing PPS Toolkit download...", wsChild|wsVisible|ssLeft, 24, 28, 500, 24, hwnd, 0)
	u.progress = createChild("msctls_progress32", "", wsChild|wsVisible, 24, 68, 500, 24, hwnd, 0)
	u.percent = createChild("STATIC", "0%", wsChild|wsVisible|ssLeft, 24, 102, 500, 24, hwnd, 0)
	u.launchButton = createChild("BUTTON", "Launch PPS Toolkit", wsChild|wsVisible|bsPushButton, 248, 166, 146, 34, hwnd, idLaunchButton)
	u.closeButton = createChild("BUTTON", "Close", wsChild|wsVisible|bsPushButton, 408, 166, 116, 34, hwnd, idCloseButton)
	procEnableWindow.Call(uintptr(u.launchButton), 0)
	procSendMessage.Call(uintptr(u.progress), pbmSetRange32, 0, 100)
}

func (u *uiState) report(event ProgressEvent) {
	u.mutex.Lock()
	u.latest = event
	u.mutex.Unlock()
	if u.hwnd != 0 {
		procPostMessage.Call(uintptr(u.hwnd), wmAppProgress, 0, 0)
	}
}

func (u *uiState) refreshProgress() {
	u.mutex.Lock()
	event := u.latest
	u.mutex.Unlock()
	setWindowText(u.status, event.Message)
	percent := 0
	if event.Total > 0 {
		percent = int(float64(event.Downloaded) * 100 / float64(event.Total))
		if percent < 0 {
			percent = 0
		}
		if percent > 100 {
			percent = 100
		}
	}
	procSendMessage.Call(uintptr(u.progress), pbmSetPos, uintptr(percent), 0)
	setWindowText(u.percent, fmt.Sprintf("%d%%", percent))
}

func (u *uiState) refreshDone() {
	u.mutex.Lock()
	err := u.err
	result := u.result
	u.mutex.Unlock()
	if err != nil {
		setWindowText(u.status, "Install failed: "+err.Error())
		setWindowText(u.percent, "The package was not installed.")
		procEnableWindow.Call(uintptr(u.launchButton), 0)
		return
	}
	setWindowText(u.status, "PPS Toolkit is ready.")
	setWindowText(u.percent, result.InstallDir)
	procSendMessage.Call(uintptr(u.progress), pbmSetPos, 100, 0)
	procEnableWindow.Call(uintptr(u.launchButton), 1)
}

func createChild(className string, text string, style uintptr, x int, y int, width int, height int, parent syscall.Handle, id uintptr) syscall.Handle {
	hwnd, _, _ := procCreateWindowEx.Call(
		0,
		uintptr(unsafe.Pointer(utf16Ptr(className))),
		uintptr(unsafe.Pointer(utf16Ptr(text))),
		style,
		uintptr(x), uintptr(y), uintptr(width), uintptr(height),
		uintptr(parent),
		id,
		0,
		0,
	)
	return syscall.Handle(hwnd)
}

func setWindowText(hwnd syscall.Handle, text string) {
	procSetWindowText.Call(uintptr(hwnd), uintptr(unsafe.Pointer(utf16Ptr(text))))
}

func utf16Ptr(value string) *uint16 {
	ptr, _ := syscall.UTF16PtrFromString(value)
	return ptr
}
