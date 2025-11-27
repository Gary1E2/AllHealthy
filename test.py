from kivy.config import Config
Config.set('kivy', 'default_font', 
    ['fonts/Roboto-Regular.ttf', 'fonts/NotoEmoji-Regular.ttf']
)

from kivy.core.text import LabelBase
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.core.window import Window
import os, sys

LabelBase.register(
    name="RobotoDefault",
    fn_regular="fonts/Roboto-Regular.ttf"
)

LabelBase.register(
    name="EmojiFallback",
    fn_regular="fonts/NotoEmoji-Regular.ttf"
)

# Ensure we are in project root so relative paths resolve
print("CWD:", os.getcwd())
print("Fonts exist:")
for f in ("fonts/Roboto-Regular.ttf", "fonts/NotoEmoji-Regular.ttf", "fonts/NotoColorEmoji.ttf"):
    print(f, "->", os.path.exists(f))

# Register optionally (not strictly necessary if Config default_font uses file paths,
# but registering gives named option to try)
if os.path.exists("fonts/Roboto-Regular.ttf"):
    LabelBase.register(name="RobotoLocal", fn_regular="fonts/Roboto-Regular.ttf")
if os.path.exists("fonts/NotoEmoji-Regular.ttf"):
    LabelBase.register(name="NotoEmojiLocal", fn_regular="fonts/NotoEmoji-Regular.ttf")
if os.path.exists("fonts/NotoColorEmoji.ttf"):
    LabelBase.register(name="NotoColorEmojiLocal", fn_regular="fonts/NotoColorEmoji.ttf")

class TestApp(App):
    def build(self):
        Window.size = (360, 240)
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        r = Label(text="Regular font text — no emoji", font_size=16, size_hint_y=None, height=40)
        e1 = Label(text="Emoji test: 😄🍎🔥", font_size=26, size_hint_y=None, height=60)
        e2 = Label(text="Mixed: Hello 😄 World 🍌", font_size=26, size_hint_y=None, height=60)

        root.add_widget(r)
        root.add_widget(e1)
        root.add_widget(e2)
        return root

if __name__ == "__main__":
    TestApp().run()

