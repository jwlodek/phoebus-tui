from phoebus_tui.widgets import Canvas


async def test_canvas_covers_the_display_size(open_widgets, make_widget, make_color):
    raw = make_color("background_color", 1, 2, 3)
    async with open_widgets(make_widget("label"), width=800, height=400, raw=raw) as (app, pilot, pvs):
        canvas = app.query_one(Canvas)
        assert canvas.size == (100, 20)
        assert canvas.styles.background.rgb == (1, 2, 3)


async def test_canvas_grows_to_fit_widgets_outside_the_display(open_widgets, make_widget):
    widget = make_widget("label", x=1000, y=900, width=80, height=20)
    async with open_widgets(widget, width=100, height=100) as (app, pilot, pvs):
        assert app.query_one(Canvas).size == (135, 46)


async def test_example_displays_load(run_app, examples_dir):
    async with run_app(examples_dir / "demo.bob", size=(160, 50)) as (app, pilot, pvs):
        await pilot.pause(0.3)
        assert app.title == "Phoebus TUI Demo - DEMO"
        assert len(app.current_tab.query("TextUpdateWidget")) > 3
