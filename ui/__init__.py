"""Everything the user sees: the chat window, Settings, onboarding, the tray icon and the hotkey.

Nothing is imported here, so a module like ui.single_instance loads on its own: a second launch
hands over to the running Nimbus without loading the whole interface and engine first.
"""
