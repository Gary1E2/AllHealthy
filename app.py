from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.progressbar import ProgressBar
from kivy.uix.image import Image
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.clock import Clock

import threading
import time
import traceback
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import modules
from chatbot import load_model, estimate_nutrition, handle_logged_meal
from upload import upload_meal, init_firebase
import datetime

# Set colours
main_colour = get_color_from_hex("#1E2D2F")
text_colour = get_color_from_hex("#BFD1E5")
accent1_colour = get_color_from_hex("#809848")
accent2_colour = get_color_from_hex("#B0CA87")
accent3_colour = get_color_from_hex("#7D4E57")

# Set main background color
Window.clearcolor = main_colour

# User configuration
USER_ID = "user"


class LoadingScreen(FloatLayout):
    """Loading screen shown during initialization"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Background
        with self.canvas.before:
            Color(*main_colour)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_bg, size=self.update_bg)
        
        # Center container
        container = BoxLayout(
            orientation="vertical",
            spacing=20,
            size_hint=(0.6, 0.4),
            pos_hint={"center_x": 0.5, "center_y": 0.5}
        )
        
        # Title
        title = Label(
            text="Diet Tracker",
            font_size=32,
            bold=True,
            color=accent2_colour,
            size_hint_y=0.3
        )
        container.add_widget(title)
        
        # Status label
        self.status_label = Label(
            text="Initializing...",
            font_size=18,
            color=text_colour,
            size_hint_y=0.2
        )
        container.add_widget(self.status_label)
        
        # Progress bar
        self.progress = ProgressBar(
            max=100,
            value=0,
            size_hint_y=0.2
        )
        container.add_widget(self.progress)
        
        # Tip label
        self.tip_label = Label(
            text="Tip: First load may take 30-60 seconds",
            font_size=14,
            color=get_color_from_hex("#808080"),
            size_hint_y=0.2
        )
        container.add_widget(self.tip_label)
        
        self.add_widget(container)
    
    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
    
    def update_status(self, status, progress):
        """Update loading status and progress bar"""
        self.status_label.text = status
        self.progress.value = progress


class ChatBubble(BoxLayout):
    def __init__(self, text, is_user=False, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, **kwargs)
        self.is_user = is_user
        
        # Background color for bubble
        bubble_color = accent3_colour if is_user else accent1_colour
        text_color = text_colour
        
        # Create bubble container with proper alignment
        if is_user:
            # User message - align right with 10% left margin
            self.size_hint_x = 1
            self.padding = [Window.width * 0.1, 5, 10, 5]
        else:
            # System message - align left with 10% right margin
            self.size_hint_x = 1
            self.padding = [10, 5, Window.width * 0.1, 5]
        
        # Bind to window resize to update padding dynamically
        Window.bind(width=self.update_padding)
        
        # Bubble background
        bubble_container = BoxLayout(size_hint_y=None, size_hint_x=1, padding=15)
        
        with bubble_container.canvas.before:
            Color(*bubble_color)
            self.rect = RoundedRectangle(radius=[15], pos=bubble_container.pos, size=bubble_container.size)
        
        bubble_container.bind(pos=self.update_rect, size=self.update_rect)
        
        # Label with dynamic sizing and proper text wrapping
        label = Label(
            text=text,
            color=text_color,
            halign="left",  # Always align left for proper wrapping
            valign="top",
            size_hint=(1, None),  # Take full width, dynamic height
            markup=True,
            text_size=(None, None)  # Will be set dynamically
        )
        
        # Set text_size width dynamically based on bubble width
        def update_text_width(instance, value):
            # Set text_size to bubble width minus padding
            label.text_size = (bubble_container.width - 30, None)
        
        bubble_container.bind(width=update_text_width)
        
        # Update label height when texture size changes
        def update_label_height(instance, value):
            label.height = value[1] + 10
            bubble_container.height = label.height + 30
            self.height = bubble_container.height + 10
        
        label.bind(texture_size=update_label_height)
        
        bubble_container.add_widget(label)
        
        # Store references for dynamic updates
        self.bubble_container = bubble_container
        self.label = label
        
        # Initial size setup - 90% of window width minus padding
        label.text_size = (Window.width * 0.9 - 50, None)
        
        self.add_widget(bubble_container)

    def update_padding(self, instance, width):
        """Update padding when window is resized"""
        if self.is_user:
            self.padding = [width * 0.1, 5, 10, 5]
        else:
            self.padding = [10, 5, width * 0.1, 5]
        
        # Update label text_size to match new width
        if hasattr(self, 'label'):
            self.label.text_size = (width * 0.9 - 50, None)

    def update_rect(self, instance, *args):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class MacrosHeader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=200, padding=15, spacing=15, **kwargs)
        
        with self.canvas.before:
            Color(*accent2_colour)
            self.rect = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        
        self.bind(pos=self.update_rect, size=self.update_rect)
        
        # Left side: Pie chart
        left_container = BoxLayout(orientation='vertical', size_hint_x=0.45, spacing=5)
        
        # Title for pie chart
        pie_title = Label(
            text="Daily Calories",
            color=get_color_from_hex("#000000"),
            font_size=16,
            bold=True,
            size_hint_y=0.15
        )
        left_container.add_widget(pie_title)
        
        # Pie chart image
        self.pie_chart_image = Image(size_hint_y=0.85)
        left_container.add_widget(self.pie_chart_image)
        
        # Right side: Progress bars for macros
        right_container = BoxLayout(orientation='vertical', size_hint_x=0.55, spacing=10, padding=[10, 5])
        
        # Title
        title = Label(
            text="Macros Progress",
            color=get_color_from_hex("#000000"),
            font_size=16,
            bold=True,
            size_hint_y=0.15
        )
        right_container.add_widget(title)
        
        # Macros progress bars container
        macros_container = BoxLayout(orientation='vertical', spacing=8, size_hint_y=0.85)
        
        # Protein
        self.protein_container = self.create_macro_bar("Protein", "#FF6B6B")
        macros_container.add_widget(self.protein_container)
        
        # Carbs
        self.carbs_container = self.create_macro_bar("Carbs", "#4ECDC4")
        macros_container.add_widget(self.carbs_container)
        
        # Fats
        self.fats_container = self.create_macro_bar("Fats", "#FFE66D")
        macros_container.add_widget(self.fats_container)
        
        right_container.add_widget(macros_container)
        
        # Add both sides to main layout
        self.add_widget(left_container)
        self.add_widget(right_container)
        
        # Store goals for percentage calculations
        self.calorie_goal = 2000
        self.protein_goal = 150
        self.carbs_goal = 250
        self.fats_goal = 65
    
    def create_macro_bar(self, label_text, bar_color):
        """Create a labeled progress bar for a macro"""
        container = BoxLayout(orientation='vertical', spacing=3)
        
        # Label row (name and value)
        label_row = BoxLayout(orientation='horizontal', size_hint_y=0.4)
        
        name_label = Label(
            text=label_text,
            color=get_color_from_hex("#000000"),
            font_size=14,
            bold=True,
            halign="left",
            size_hint_x=0.5
        )
        name_label.bind(size=name_label.setter('text_size'))
        
        value_label = Label(
            text="0/0g (0%)",
            color=get_color_from_hex("#000000"),
            font_size=12,
            halign="right",
            size_hint_x=0.5
        )
        value_label.bind(size=value_label.setter('text_size'))
        
        label_row.add_widget(name_label)
        label_row.add_widget(value_label)
        
        # Progress bar with custom styling
        progress_container = BoxLayout(size_hint_y=0.6)
        
        # Background for progress bar
        with progress_container.canvas.before:
            Color(0.8, 0.8, 0.8, 1)
            progress_container.bg_rect = RoundedRectangle(
                radius=[5],
                pos=progress_container.pos,
                size=progress_container.size
            )
        
        progress_container.bind(
            pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val),
            size=lambda obj, val: setattr(obj.bg_rect, 'size', val)
        )
        
        # Colored progress bar overlay
        progress_bar = BoxLayout()
        with progress_bar.canvas.before:
            Color(*get_color_from_hex(bar_color))
            progress_bar.bar_rect = RoundedRectangle(
                radius=[5],
                pos=progress_bar.pos,
                size=(0, progress_bar.height)
            )
        
        progress_bar.bind(pos=lambda obj, val: setattr(obj.bar_rect, 'pos', val))
        
        progress_container.add_widget(progress_bar)
        
        container.add_widget(label_row)
        container.add_widget(progress_container)
        
        # Store references
        container.value_label = value_label
        container.progress_bar = progress_bar
        container.bar_color = bar_color
        
        return container
    
    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
    
    def create_pie_chart(self, consumed, remaining):
        """Generate pie chart for calories"""
        fig, ax = plt.subplots(figsize=(3, 3), facecolor='none')
        
        # Data
        sizes = [consumed, max(0, remaining)]
        labels = [f'Consumed\n{int(consumed)}', f'Remaining\n{int(remaining)}']
        colors = ['#FF6B6B' if remaining < 0 else '#4ECDC4', '#E0E0E0']
        
        # If over goal, show as 100% consumed + excess
        if remaining < 0:
            sizes = [self.calorie_goal, abs(remaining)]
            labels = [f'Goal\n{int(self.calorie_goal)}', f'Over\n{int(abs(remaining))}']
            colors = ['#FFE66D', '#FF6B6B']
        
        # Create pie chart
        wedges, texts = ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            startangle=90,
            textprops={'fontsize': 10, 'weight': 'bold', 'color': '#000000'}
        )
        
        ax.axis('equal')
        
        # Save to BytesIO
        buf = BytesIO()
        plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', dpi=80)
        buf.seek(0)
        plt.close(fig)
        
        return buf
    
    def update_progress_bar(self, container, current, goal):
        """Update a single progress bar"""
        percentage = min((current / goal * 100) if goal > 0 else 0, 100)
        over_percentage = max((current / goal * 100) if goal > 0 else 0, 100)
        
        # Update label
        container.value_label.text = f"{int(current)}/{int(goal)}g ({int(over_percentage)}%)"
        
        # Change color if over goal
        if current > goal:
            container.value_label.color = get_color_from_hex("#8B0000")
            bar_color = "#8B0000"
        else:
            container.value_label.color = get_color_from_hex("#000000")
            bar_color = container.bar_color
        
        # Update progress bar width
        progress_bar = container.progress_bar
        with progress_bar.canvas.before:
            progress_bar.canvas.before.clear()
            Color(*get_color_from_hex(bar_color))
            progress_bar.bar_rect = RoundedRectangle(
                radius=[5],
                pos=progress_bar.pos,
                size=(progress_bar.parent.width * (percentage / 100), progress_bar.height)
            )
        
        # Bind size update
        def update_bar_size(obj, val):
            progress_bar.bar_rect.pos = obj.pos
            progress_bar.bar_rect.size = (obj.width * (percentage / 100), obj.height)
        
        progress_bar.parent.unbind(pos=update_bar_size, size=update_bar_size)
        progress_bar.parent.bind(pos=update_bar_size, size=update_bar_size)
    
    def set_data(self, macros_consumed, macros_goals=None):
        """
        Update display with consumed macros
        
        Args:
            macros_consumed: dict with 'calories', 'proteins', 'carbs', 'fats' (consumed amounts)
            macros_goals: dict with 'calories', 'proteins', 'carbs', 'fats' (goal amounts)
        """
        # Update goals if provided
        if macros_goals:
            self.calorie_goal = macros_goals.get('calories', 2000)
            self.protein_goal = macros_goals.get('proteins', 150)
            self.carbs_goal = macros_goals.get('carbs', 250)
            self.fats_goal = macros_goals.get('fats', 65)
        
        # Get consumed values
        calories_consumed = macros_consumed.get('calories', 0)
        protein_consumed = macros_consumed.get('proteins', 0)
        carbs_consumed = macros_consumed.get('carbs', 0)
        fats_consumed = macros_consumed.get('fats', 0)
        
        # Update pie chart
        calories_remaining = self.calorie_goal - calories_consumed
        pie_buf = self.create_pie_chart(calories_consumed, calories_remaining)
        
        # Convert to Kivy image
        core_image = CoreImage(pie_buf, ext='png')
        self.pie_chart_image.texture = core_image.texture
        
        # Update progress bars
        self.update_progress_bar(self.protein_container, protein_consumed, self.protein_goal)
        self.update_progress_bar(self.carbs_container, carbs_consumed, self.carbs_goal)
        self.update_progress_bar(self.fats_container, fats_consumed, self.fats_goal)


class ChatScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=10, spacing=10, **kwargs)
        
        self.current_meal_type = "breakfast"  # Default meal type
        
        # Macros header
        self.macros_header = MacrosHeader()
        self.add_widget(self.macros_header)
        
        # Load macro data from Firebase
        Clock.schedule_once(lambda dt: self.load_macros_data(), 1.0)
        
        # Scrollable chat history
        self.scroll = ScrollView(size_hint=(1, 0.75))
        self.chat_history = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=10)
        self.chat_history.bind(minimum_height=self.chat_history.setter("height"))
        self.scroll.add_widget(self.chat_history)
        self.add_widget(self.scroll)

        # Input area
        input_area = BoxLayout(size_hint=(1, 0.12), spacing=10)

        # Set up chat input area and get the layout
        self.chat_area = self.setup_chat_input()

        # Single "Log Meal" button
        self.log_meal_button = Button(
            text="Log\nMeal",
            background_normal="",
            background_color=accent1_colour,
            color=text_colour,
            size_hint=(0.2, 1),
            bold=True,
            font_size=16
        )
        self.log_meal_button.bind(on_press=self.open_meal_logging_screen)

        input_area.add_widget(self.chat_area)
        input_area.add_widget(self.log_meal_button)
        self.add_widget(input_area)
        
        # Welcome message
        Clock.schedule_once(
            lambda dt: self.add_message(
                "Welcome to Diet Tracker!\nTap 'Log Meal' to record your meals via image or manual entry.",
                is_user=False
            ),
            0.5
        )


    def setup_chat_input(self):
        """Setup the chatbot text input at the bottom of the screen"""
        # Create a horizontal layout for the input box and send button
        input_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=60,
            spacing=10,
            padding=[10, 5, 10, 10]
        )
        
        # Text input field
        text_input = TextInput(
            hint_text="Ask me anything about nutrition...",
            multiline=False,
            size_hint_x=0.8,
            background_color=(1, 1, 1, 0.1),
            foreground_color=text_colour,
            cursor_color=text_colour,
            font_size=16
        )
        
        # Store the text input widget and bind Enter key to send message
        self.chat_input = text_input
        self.chat_input.bind(on_text_validate=self.send_chat_message)
        
        # Send button
        send_btn = Button(
            text="Send",
            size_hint_x=0.2,
            background_normal="",
            background_color=accent1_colour,
            color=text_colour,
            font_size=16
        )
        send_btn.bind(on_release=self.send_chat_message)
        
        # Add widgets to the layout
        input_layout.add_widget(text_input)  # text_input is already stored in self.chat_input
        input_layout.add_widget(send_btn)
        
        return input_layout
    

    def send_chat_message(self, instance):
        """Handle sending a chat message to the LLM"""
        user_message = self.chat_input.text.strip()
        
        # Validate input
        if not user_message:
            return
        
        # Clear input field
        self.chat_input.text = ""
        
        # Display user message
        self.add_message(user_message, is_user=True)
        
        # Show typing indicator (optional)
        self.add_message("Thinking...", is_user=False)
        
        # Process in background thread
        threading.Thread(
            target=self.process_chat_message,
            args=(user_message,),
            daemon=True
        ).start()


    def process_chat_message(self, user_message):
        """Process chat message with LLM in background thread"""
        try:
            # Import your chatbot function
            from chatbot import get_chat_response  # We'll create this next
            
            # Get user's current macro data for context (optional)
            context = None
            if hasattr(self, 'total_daily_macros'):
                context = {
                    'daily_macros': self.total_daily_macros,
                    'user_id': USER_ID
                }
            
            # Get response from LLM
            response = get_chat_response(user_message, context)
            
            # Remove "Thinking..." message and add real response
            Clock.schedule_once(
                lambda dt: self.remove_last_message(),  # Remove "Thinking..."
                0
            )
            Clock.schedule_once(
                lambda dt: self.add_message(response, is_user=False),
                0
            )
            
        except Exception as e:
            import traceback
            print(f"[ERROR] Chat processing failed: {e}")
            traceback.print_exc()
            
            Clock.schedule_once(
                lambda dt: self.remove_last_message(),
                0
            )
            Clock.schedule_once(
                lambda dt: self.add_message("Sorry, I couldn't process that. Please try again.", is_user=False),
                0
            )


    def load_macros_data(self):
        """Load daily macros goal and calculate consumed macros from macros_left"""
        def load_in_thread():
            try:
                db = init_firebase()
                if db is None:
                    # Fallback to defaults
                    default_consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
                    default_goals = {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}
                    Clock.schedule_once(lambda dt: self.macros_header.set_data(default_consumed, default_goals), 0)
                    return
                
                # Get user's daily macros goal
                user_ref = db.collection('users').document(USER_ID)
                user_doc = user_ref.get()
                
                if user_doc.exists:
                    data = user_doc.to_dict()
                    daily_goal = data.get('daily_macros_goal', {
                        'calories': 2000,
                        'proteins': 150,
                        'carbs': 250,
                        'fats': 65
                    })
                else:
                    daily_goal = {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}
                
                # Get today's meal logs
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                meal_ref = db.collection('users').document(USER_ID).collection('mealLogs').document(today_str)
                meal_doc = meal_ref.get()
                
                # Initialize consumed macros
                total_consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
                
                if meal_doc.exists:
                    meal_data = meal_doc.to_dict()
                    
                    # Check if macros_left exists in Firebase
                    if 'macros_left' in meal_data:
                        macros_left = meal_data['macros_left']
                        
                        # Calculate consumed from: consumed = goal - remaining
                        total_consumed = {
                            'calories': daily_goal.get('calories', 2000) - macros_left.get('calories', 0),
                            'proteins': daily_goal.get('proteins', 150) - macros_left.get('proteins', 0),
                            'carbs': daily_goal.get('carbs', 250) - macros_left.get('carbs', 0),
                            'fats': daily_goal.get('fats', 65) - macros_left.get('fats', 0)
                        }
                    else:
                        # macros_left doesn't exist, calculate manually from meals
                        for meal_type in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                            if meal_type in meal_data and isinstance(meal_data[meal_type], dict):
                                meal = meal_data[meal_type]
                                total_consumed['calories'] += meal.get('calories', 0)
                                total_consumed['proteins'] += meal.get('proteins', 0)
                                total_consumed['carbs'] += meal.get('carbs', 0)
                                total_consumed['fats'] += meal.get('fats', 0)
                        
                        # Calculate and store macros_left for future use
                        macros_left = {
                            'calories': daily_goal.get('calories', 2000) - total_consumed['calories'],
                            'proteins': daily_goal.get('proteins', 150) - total_consumed['proteins'],
                            'carbs': daily_goal.get('carbs', 250) - total_consumed['carbs'],
                            'fats': daily_goal.get('fats', 65) - total_consumed['fats']
                        }
                        
                        try:
                            meal_ref.set({'macros_left': macros_left}, merge=True)
                        except:
                            pass  # Ignore if write fails
                
                # Store total macros consumed for LLM reference (keep your existing format)
                self.total_daily_macros = {
                    'Calories': total_consumed['calories'],
                    'Protein': total_consumed['proteins'],
                    'Carbs': total_consumed['carbs'],
                    'Fats': total_consumed['fats']
                }
                
                # Update macros header with consumed and goals
                Clock.schedule_once(
                    lambda dt: self.macros_header.set_data(total_consumed, daily_goal), 
                    0
                )
                
            except Exception as e:
                traceback.print_exc()
                default_consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
                default_goals = {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}
                Clock.schedule_once(lambda dt: self.macros_header.set_data(default_consumed, default_goals), 0)
        
        threading.Thread(target=load_in_thread, daemon=True).start()


    def add_message(self, message, is_user=False):
        """Add message to chat - must be called from main thread"""
        bubble = ChatBubble(message, is_user=is_user)
        self.chat_history.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0.1)

    def remove_last_message(self):
        """Remove the last message from the chat history"""
        if self.chat_history.children:  # Check if there are any messages
            self.chat_history.remove_widget(self.chat_history.children[0])


    def open_meal_logging_screen(self, instance):
        """Open the dedicated meal logging screen"""
        meal_logging_screen = MealLoggingScreen(self)
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(meal_logging_screen)


class MealSurveyPopup(Popup):
    def __init__(self, on_submit_callback, **kwargs):
        super().__init__(**kwargs)
        self.on_submit_callback = on_submit_callback
        self.title = "Rate Your Current State"
        self.size_hint = (0.9, 0.6)
        self.auto_dismiss = False
        
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Energy Level Section
        layout.add_widget(Label(
            text="Energy Level (1=Very Low, 5=Very High)",
            size_hint_y=0.2
        ))
        self.energy_slider = Slider(
            min=1, max=5, value=3, step=1,
            size_hint_y=0.2
        )
        self.energy_label = Label(text="3", size_hint_y=0.15)
        self.energy_slider.bind(value=lambda instance, value: setattr(self.energy_label, 'text', str(int(value))))
        layout.add_widget(self.energy_slider)
        layout.add_widget(self.energy_label)
        
        # Hunger Level Section
        layout.add_widget(Label(
            text="Hunger Level (1=Not Hungry, 5=Very Hungry)",
            size_hint_y=0.2
        ))
        self.hunger_slider = Slider(
            min=1, max=5, value=3, step=1,
            size_hint_y=0.2
        )
        self.hunger_label = Label(text="3", size_hint_y=0.15)
        self.hunger_slider.bind(value=lambda instance, value: setattr(self.hunger_label, 'text', str(int(value))))
        layout.add_widget(self.hunger_slider)
        layout.add_widget(self.hunger_label)
        
        # Submit Button
        submit_btn = Button(
            text="Submit",
            size_hint_y=0.25,
            background_color=(0.2, 0.6, 1, 1)
        )
        submit_btn.bind(on_press=self.submit)
        layout.add_widget(submit_btn)
        
        self.content = layout
    
    def submit(self, instance):
        energy = int(self.energy_slider.value)
        hunger = int(self.hunger_slider.value)
        self.on_submit_callback(energy, hunger)
        self.dismiss()


class MealLoggingScreen(BoxLayout):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=15, **kwargs)
        self.chat_screen = chat_screen  # Reference to go back
        self.selected_image_path = None
        
        with self.canvas.before:
            Color(*main_colour)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_bg, size=self.update_bg)
        
        # Header with back button
        header = BoxLayout(size_hint_y=None, height=60, spacing=10)
        
        back_btn = Button(
            text="← Back",
            size_hint_x=0.2,
            background_normal="",
            background_color=accent3_colour,
            color=text_colour,
            font_size=18
        )
        back_btn.bind(on_press=self.go_back)
        
        header_title = Label(
            text="Log Meal",
            font_size=24,
            bold=True,
            color=accent2_colour,
            size_hint_x=0.8
        )
        
        header.add_widget(back_btn)
        header.add_widget(header_title)
        self.add_widget(header)
        
        # Scrollable content area
        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=20, padding=10)
        content.bind(minimum_height=content.setter('height'))
        
        # Section 1: Meal Type Selection
        meal_section = BoxLayout(orientation='vertical', size_hint_y=None, height=100, spacing=10)
        meal_label = Label(
            text="Select Meal Type:",
            font_size=18,
            bold=True,
            color=text_colour,
            size_hint_y=0.4,
            halign='left'
        )
        meal_label.bind(size=meal_label.setter('text_size'))
        
        from kivy.uix.spinner import Spinner
        self.meal_spinner = Spinner(
            text=self.chat_screen.current_meal_type.capitalize(),
            values=["Breakfast", "Lunch", "Dinner", "Supper", "Snacks"],
            size_hint_y=0.6,
            background_color=accent2_colour,
            color=get_color_from_hex("#000000"),
            font_size=16
        )
        
        meal_section.add_widget(meal_label)
        meal_section.add_widget(self.meal_spinner)
        content.add_widget(meal_section)
        
        # Divider
        divider1 = Label(
            text="=" * 50,
            size_hint_y=None,
            height=30,
            color=accent2_colour
        )
        content.add_widget(divider1)
        
        # Section 2: Image Upload & Analysis
        image_section = BoxLayout(orientation='vertical', size_hint_y=None, height=200, spacing=10)
        
        image_title = Label(
            text="Option 1: Upload & Analyze Image",
            font_size=18,
            bold=True,
            color=accent2_colour,
            size_hint_y=0.2,
            halign='left'
        )
        image_title.bind(size=image_title.setter('text_size'))
        
        self.image_status = Label(
            text="No image selected",
            font_size=14,
            color=text_colour,
            size_hint_y=0.2,
            halign='center'
        )
        
        image_buttons = BoxLayout(size_hint_y=0.3, spacing=10)
        
        upload_btn = Button(
            text="Upload Image",
            background_normal="",
            background_color=accent2_colour,
            color=get_color_from_hex("#000000"),
            font_size=16
        )
        upload_btn.bind(on_press=self.upload_image)
        
        self.analyze_btn = Button(
            text="Analyze & Log",
            background_normal="",
            background_color=accent1_colour,
            color=text_colour,
            font_size=16,
            disabled=True
        )
        self.analyze_btn.bind(on_press=self.analyze_image)
        
        image_buttons.add_widget(upload_btn)
        image_buttons.add_widget(self.analyze_btn)
        
        image_section.add_widget(image_title)
        image_section.add_widget(self.image_status)
        image_section.add_widget(image_buttons)
        content.add_widget(image_section)
        
        # Divider
        divider2 = Label(
            text="=" * 50,
            size_hint_y=None,
            height=30,
            color=accent2_colour
        )
        content.add_widget(divider2)
        
        # Section 3: Manual Entry
        manual_section = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        manual_section.bind(minimum_height=manual_section.setter('height'))
        
        manual_title = Label(
            text="Option 2: Enter Manually",
            font_size=18,
            bold=True,
            color=accent2_colour,
            size_hint_y=None,
            height=40,
            halign='left'
        )
        manual_title.bind(size=manual_title.setter('text_size'))
        manual_section.add_widget(manual_title)
        
        # Input fields
        fields = ["Calories", "Proteins", "Carbs", "Fats"]
        self.input_boxes = {}
        
        for field in fields:
            row = BoxLayout(size_hint_y=None, height=60, spacing=10)
            
            field_label = Label(
                text=f"{field}:",
                size_hint_x=0.3,
                color=text_colour,
                font_size=16,
                bold=True
            )
            
            input_field = TextInput(
                hint_text=f"Enter {field.lower()}",
                multiline=False,
                input_filter='float',
                size_hint_x=0.7,
                background_color=(1, 1, 1, 0.1),
                foreground_color=text_colour,
                cursor_color=text_colour,
                font_size=16
            )
            
            self.input_boxes[field.lower()] = input_field
            row.add_widget(field_label)
            row.add_widget(input_field)
            manual_section.add_widget(row)
        
        # Manual submit button
        manual_submit_btn = Button(
            text="Log Meal Manually",
            size_hint_y=None,
            height=60,
            background_normal="",
            background_color=accent1_colour,
            color=text_colour,
            font_size=18,
            bold=True
        )
        manual_submit_btn.bind(on_press=self.submit_manual)
        manual_section.add_widget(manual_submit_btn)
        
        content.add_widget(manual_section)
        
        scroll.add_widget(content)
        self.add_widget(scroll)
    
    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
    
    def go_back(self, instance):
        """Return to chat screen"""
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(self.chat_screen)
    
    def upload_image(self, instance):
        """Open file chooser to select an image"""
        content = BoxLayout(orientation="vertical", spacing=10)
        
        chooser = FileChooserListView(
            path=".",
            filters=["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
        )
        
        button_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        select_btn = Button(text="Select", background_color=accent1_colour)
        cancel_btn = Button(text="Cancel", background_color=accent3_colour)
        
        button_layout.add_widget(select_btn)
        button_layout.add_widget(cancel_btn)
        
        content.add_widget(chooser)
        content.add_widget(button_layout)
        
        popup = Popup(
            title="Select a meal image",
            content=content,
            size_hint=(0.9, 0.9)
        )
        
        def on_select(instance):
            if chooser.selection:
                self.selected_image_path = chooser.selection[0]
                filename = self.selected_image_path.split('/')[-1].split('\\')[-1]
                self.image_status.text = f"Selected: {filename}"
                self.analyze_btn.disabled = False
                popup.dismiss()
        
        def on_cancel(instance):
            popup.dismiss()
        
        select_btn.bind(on_press=on_select)
        cancel_btn.bind(on_press=on_cancel)
        
        popup.open()
    
    def analyze_image(self, instance):
        """Analyze selected image and log meal"""
        if not self.selected_image_path:
            return
        
        meal_type = self.meal_spinner.text.lower()
        self.analyze_btn.disabled = True
        self.image_status.text = "Analyzing... (10-30 seconds)"
        
        def analyze_in_thread():
            try:
                # Analyze with LLM
                nutrition_data = estimate_nutrition(self.selected_image_path)
                
                if nutrition_data is None:
                    Clock.schedule_once(
                        lambda dt: setattr(self.image_status, 'text', "Analysis failed. Try again."),
                        0
                    )
                    Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
                    return
                
                # Upload to Firebase
                today = datetime.date.today().strftime("%Y-%m-%d")
                success = upload_meal(USER_ID, meal_type, nutrition_data, today)
                
                if success:
                    Clock.schedule_once(
                        lambda dt: setattr(self.image_status, 'text', f"✓ Logged successfully!"),
                        0
                    )
                    
                    # Update chat screen's meal type (FIXED - removed button reference)
                    self.chat_screen.current_meal_type = meal_type
                    
                    # Add message to chat
                    result_text = (
                        f"{meal_type.capitalize()} logged:\n"
                        f"Calories: {nutrition_data.get('Calories')} kcal\n"
                        f"Protein: {nutrition_data.get('Protein')} g\n"
                        f"Carbs: {nutrition_data.get('Carbs')} g\n"
                        f"Fats: {nutrition_data.get('Fats')} g"
                    )
                    Clock.schedule_once(
                        lambda dt: self.chat_screen.add_message(result_text, is_user=False),
                        0
                    )
                    
                    # Refresh macros
                    Clock.schedule_once(lambda dt: self.chat_screen.load_macros_data(), 1.5)
                    
                    # Show survey popup
                    def on_survey_submitted(energy_level, hunger_level):
                        def generate_tips():
                            try:
                                time.sleep(1.0)
                                advice = handle_logged_meal(
                                    meal_type,
                                    nutrition_data,
                                    self.chat_screen.total_daily_macros,
                                    energy_level=energy_level,
                                    hunger_level=hunger_level
                                )
                                
                                if advice:
                                    Clock.schedule_once(
                                        lambda dt: self.chat_screen.add_message(advice.strip(), is_user=False),
                                        0
                                    )
                                else:
                                    Clock.schedule_once(
                                        lambda dt: self.chat_screen.add_message("All nutrients within range. 👍", is_user=False),
                                        0
                                    )
                            except Exception as e:
                                print(f"[ERROR] Tips generation: {e}")
                                traceback.print_exc()
                        
                        threading.Thread(target=generate_tips, daemon=True).start()
                    
                    Clock.schedule_once(
                        lambda dt: MealSurveyPopup(on_submit_callback=on_survey_submitted).open(),
                        1.0
                    )
                    
                    # Go back to chat after delay
                    Clock.schedule_once(lambda dt: self.go_back(None), 2.5)
                else:
                    Clock.schedule_once(
                        lambda dt: setattr(self.image_status, 'text', "Upload failed. Try again."),
                        0
                    )
                    Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
                
            except Exception as e:
                print(f"[ERROR] Image analysis: {e}")
                traceback.print_exc()
                Clock.schedule_once(
                    lambda dt: setattr(self.image_status, 'text', f"Error: {str(e)}"),
                    0
                )
                Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
        
        threading.Thread(target=analyze_in_thread, daemon=True).start()
    
    def submit_manual(self, instance):
        """Submit manually entered meal data"""
        meal_type = self.meal_spinner.text.lower()
        
        # Validate
        if not self.input_boxes["calories"].text.strip():
            self.image_status.text = "Please enter at least calories!"
            return
        
        # Convert to nutrition data
        try:
            nutrition_data = {
                "Calories": int(float(self.input_boxes["calories"].text)) if self.input_boxes["calories"].text else 0,
                "Protein": int(float(self.input_boxes["proteins"].text)) if self.input_boxes["proteins"].text else 0,
                "Carbs": int(float(self.input_boxes["carbs"].text)) if self.input_boxes["carbs"].text else 0,
                "Fats": int(float(self.input_boxes["fats"].text)) if self.input_boxes["fats"].text else 0,
            }
        except ValueError:
            self.image_status.text = "Invalid numbers entered!"
            return
        
        # Upload to Firebase
        today = datetime.date.today().strftime("%Y-%m-%d")
        success = upload_meal(USER_ID, meal_type, nutrition_data, today)
        
        if success:
            # Update chat screen (FIXED - removed button reference)
            self.chat_screen.current_meal_type = meal_type
            
            # Add message
            result_text = (
                f"{meal_type.capitalize()} logged:\n"
                f"Calories: {nutrition_data.get('Calories')} kcal\n"
                f"Protein: {nutrition_data.get('Protein')} g\n"
                f"Carbs: {nutrition_data.get('Carbs')} g\n"
                f"Fats: {nutrition_data.get('Fats')} g"
            )
            self.chat_screen.add_message(result_text, is_user=False)
            
            # Refresh macros
            Clock.schedule_once(lambda dt: self.chat_screen.load_macros_data(), 1.5)
            
            # Show survey popup
            def on_survey_submitted(energy_level, hunger_level):
                def generate_tips():
                    try:
                        time.sleep(1.0)
                        advice = handle_logged_meal(
                            meal_type,
                            nutrition_data,
                            self.chat_screen.total_daily_macros,
                            energy_level=energy_level,
                            hunger_level=hunger_level
                        )
                        
                        if advice:
                            Clock.schedule_once(
                                lambda dt: self.chat_screen.add_message(advice.strip(), is_user=False),
                                0
                            )
                        else:
                            Clock.schedule_once(
                                lambda dt: self.chat_screen.add_message("All nutrients within range. 👍", is_user=False),
                                0
                            )
                    except Exception as e:
                        print(f"[ERROR] Tips generation: {e}")
                        traceback.print_exc()
                
                threading.Thread(target=generate_tips, daemon=True).start()
            
            MealSurveyPopup(on_submit_callback=on_survey_submitted).open()
            
            # Go back after delay
            Clock.schedule_once(lambda dt: self.go_back(None), 2.5)
        else:
            self.image_status.text = "Upload failed. Please try again."


class DietChatApp(App):
    def build(self):
        self.title = "Diet Tracker"
        
        # Show loading screen first
        self.loading_screen = LoadingScreen()
        self.main_screen = None
        
        # Start initialization in background
        Clock.schedule_once(lambda dt: self.initialize_app(), 0.1)
        
        return self.loading_screen
    
    def initialize_app(self):
        """Initialize model and Firebase in background"""
        def init_in_thread():
            try:
                # Step 1: Initialize Firebase
                Clock.schedule_once(lambda dt: self.loading_screen.update_status("Connecting to Firebase...", 20), 0)
                db = init_firebase()
                
                if db is None:
                    print("[WARNING] Firebase initialization failed, continuing anyway...")
                
                # Step 2: Load model
                Clock.schedule_once(lambda dt: self.loading_screen.update_status("Loading AI model... (30-60 sec)", 50), 0)
                model, processor = load_model()
                
                Clock.schedule_once(lambda dt: self.loading_screen.update_status("Model loaded ✓", 90), 0)
                
                # Step 3: Switch to main screen
                Clock.schedule_once(lambda dt: self.loading_screen.update_status("Starting app...", 95), 0)
                Clock.schedule_once(lambda dt: self.switch_to_main_screen(), 0.5)
                
            except Exception as e:
                traceback.print_exc()
                Clock.schedule_once(
                    lambda dt: self.loading_screen.update_status(f"Error: {str(e)}", 0),
                    0
                )
        
        threading.Thread(target=init_in_thread, daemon=True).start()
    
    def switch_to_main_screen(self):
        """Switch from loading screen to main chat screen"""
        self.loading_screen.update_status("Ready!", 100)
        self.main_screen = ChatScreen()
        self.root.clear_widgets()
        self.root.add_widget(self.main_screen)


if __name__ == "__main__":
    DietChatApp().run()