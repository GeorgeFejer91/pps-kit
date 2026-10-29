//! Keep Rust file pickers without replacing the browser's synchronous dialogs.
//!
//! The pinned dialog plugin's only setup hook registers its Rust `Dialog` state.
//! Its JavaScript initialization replaces `window.confirm` with an async IPC call,
//! which is incompatible with the shared frontends' synchronous discard guards.
//! Delegate native setup, but retain `Plugin`'s default no-script/no-IPC methods.

use tauri::{plugin::Plugin, AppHandle, Runtime};

struct NativeFileDialogs<P>(P);

pub(crate) fn init<R: Runtime>() -> impl Plugin<R> {
    NativeFileDialogs(tauri_plugin_dialog::init::<R>())
}

impl<R: Runtime, P: Plugin<R>> Plugin<R> for NativeFileDialogs<P> {
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

    // No native app handle or GUI-bearing plugin destructor is required to
    // verify the public trait boundary in a manifest-free Rust test EXE.
    struct DialogPlugin;

    impl Plugin<tauri::Wry> for DialogPlugin {
        fn name(&self) -> &'static str {
            "dialog"
        }

        fn initialization_script(&self) -> Option<String> {
            Some("window.confirm = async () => false;".to_owned())
        }
    }

    #[test]
    fn retains_native_plugin_identity_without_injecting_dialog_overrides() {
        let original = DialogPlugin;
        assert_eq!(original.name(), "dialog");
        assert!(original.initialization_script().is_some());
        assert!(original.initialization_script_2().is_some());
        let native = NativeFileDialogs(original);
        assert_eq!(native.name(), "dialog");
        assert!(native.initialization_script().is_none());
        assert!(native.initialization_script_2().is_none());
    }
}
