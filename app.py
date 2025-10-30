from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup


class ChatScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)

        # Scrollable chat history
        self.scroll = ScrollView(size_hint=(1, 0.8))
        self.chat_history = BoxLayout(orientation="vertical", size_hint_y=None)
        self.chat_history.bind(minimum_height=self.chat_history.setter("height"))
        self.scroll.add_widget(self.chat_history)
        self.add_widget(self.scroll)

        # Input + Buttons
        input_area = BoxLayout(size_hint=(1, 0.1))
        self.user_input = TextInput(hint_text="Type your message...", multiline=False)
        send_button = Button(text="Send", size_hint=(0.2, 1))
        send_button.bind(on_press=self.send_message)
        upload_button = Button(text="📷", size_hint=(0.15, 1))
        upload_button.bind(on_press=self.open_upload_popup)

        input_area.add_widget(upload_button)
        input_area.add_widget(self.user_input)
        input_area.add_widget(send_button)
        self.add_widget(input_area)

    def send_message(self, instance):
        text = self.user_input.text.strip()
        if text:
            self.add_message("You: " + text)
            self.user_input.text = ""

    def add_message(self, message):
        msg = Label(
            text=message,
            size_hint_y=None,
            height=40,
            halign="left",
            valign="middle",
            text_size=(self.width - 50, None),
        )
        msg.bind(texture_size=lambda instance, size: setattr(instance, 'height', size[1]))
        self.chat_history.add_widget(msg)
        self.scroll.scroll_y = 0  # auto scroll to latest

    def open_upload_popup(self, instance):
        # Simple file chooser popup for now (simulate image upload)
        chooser = FileChooserListView(path=".", filters=["*.png", "*.jpg", "*.jpeg"])
        popup = Popup(title="Select an image", content=chooser, size_hint=(0.9, 0.9))

        def on_file_selected(chooser, selection):
            if selection:
                self.add_message(f"📷 Image selected: {selection[0]}")
                popup.dismiss()

        chooser.bind(on_submit=on_file_selected)
        popup.open()


class DietChatApp(App):
    def build(self):
        return ChatScreen()


if __name__ == "__main__":
    DietChatApp().run()
