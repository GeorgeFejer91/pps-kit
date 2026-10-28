//! Keep Rust file pickers without replacing the browser's synchronous dialogs.
//!
//! The pinned dialog plugin's only setup hook registers its Rust `Dialog` state.
//! Its JavaScript initialization replaces `window.confirm` with an async IPC call,
//! which is incompatible with the shared frontends' synchronous discard guards.
//! Delegate native setup, but retain `Plugin`'s default no-script/no-IPC methods.

use tauri::{
    plugin::{Plugin, TauriPlugin},
    AppHandle, Runtime,
};

struct NativeFileDialogs<R: Runtime>(TauriPlugin<R>);

pub(crate) fn init<R: Runtime>() -> impl Plugin<R> {
    NativeFileDialogs(tauri_plugin_dialog::init())
}

impl<R: Runtime> Plugin<R> for NativeFileDialogs<R> {
    fn name(&self) -> &'static str {
        self.0.name()
    }

    fn initialize(
        &mut self,
        app: &AppHandle<R>,
        config: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.0.initialize(app, config)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retains_native_plugin_identity_without_injecting_dialog_overrides() {
        // Exercise the public plugin boundary without linking the upstream
        // GUI message-dialog constructor into a manifest-free Rust test EXE.
        let original = tauri::plugin::Builder::<tauri::Wry>::new("dialog")
            .js_init_script("window.confirm = async () => false;".to_owned())
            .build();
        assert_eq!(original.name(), "dialog");
        assert!(original.initialization_script().is_some());
        assert!(original.initialization_script_2().is_some());
        let native = NativeFileDialogs(original);
        assert_eq!(native.name(), "dialog");
        assert!(native.initialization_script().is_none());
        assert!(native.initialization_script_2().is_none());
    }
}
