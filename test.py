import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

def on_button_clicked(button, popover, window):
    # Get the window's allocation to calculate its canvas area
    allocation = window.get_allocation()
    # Set the popover to point to a specific location on the window's canvas
    # Example: Center of the window
    x = allocation.width // 2
    y = allocation.height // 2
    rect = Gdk.Rectangle()
    rect.x = x
    rect.y = y
    rect.width = 1
    rect.height = 1
    popover.set_pointing_to(rect)
    popover.popup()

def on_activate(app):
    # Create the main window
    window = Gtk.ApplicationWindow(application=app)
    window.set_default_size(400, 300)

    # Create a box to hold the button (or other widgets)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    window.set_child(box)

    # Create a button to trigger the popover
    button = Gtk.Button(label="Show Popover")
    box.append(button)

    # Create a popover
    popover = Gtk.Popover()
    popover.set_parent(window)  # Attach the popover to the window

    # Create content for the popover
    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    label = Gtk.Label(label="This is a popover over the window canvas!")
    close_button = Gtk.Button(label="Close Popover")
    content_box.append(label)
    content_box.append(close_button)
    popover.set_child(content_box)

    # Connect the close button to hide the popover
    close_button.connect("clicked", lambda btn: popover.popdown())

    # Connect the main button to show the popover
    button.connect("clicked", on_button_clicked, popover, window)

    # Optional: Set the popover's position (e.g., relative to the canvas)
    popover.set_position(Gtk.PositionType.BOTTOM)

    # Show the window
    window.present()

def main():
    # Create the application
    app = Gtk.Application(application_id="com.example.WindowPopoverExample")
    app.connect("activate", on_activate)
    app.run()

if __name__ == "__main__":
    main()
