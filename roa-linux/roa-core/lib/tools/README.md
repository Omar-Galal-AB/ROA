# ROA Development Tools

## Qt Designer to UE5/Python Converter

Converts Qt Designer `.ui` files to UE5 C++ or Python code.

### Usage

```bash
# Convert to UE5
python qt_to_ue5_converter.py my_widget.ui --format ue5 --output-dir output/

# Convert to Python
python qt_to_ue5_converter.py my_widget.ui --format python --output-dir output/
```

### Supported Widgets

- QPushButton → UButton
- QSlider → USlider
- QLabel → UTextBlock
- QLineEdit → UEditableTextBox
- And more...

### Output

- **UE5**: Generates `.h` and `.cpp` files ready for UE5 plugin
- **Python**: Generates `.py` file with PyQt5 code
