#!/usr/bin/env python3
"""
Qt Designer to UE5 Widget Converter
Automatically converts Qt Designer .ui files to UE5 Slate/UMG widgets
"""

import xml.etree.ElementTree as ET
import argparse
import os
from typing import Dict, List


class QtToUE5Converter:
    """Convert Qt Designer .ui files to UE5 widget code"""
    
    WIDGET_MAPPING = {
        'QPushButton': 'UButton',
        'QSlider': 'USlider',
        'QLabel': 'UTextBlock',
        'QLineEdit': 'UEditableTextBox',
        'QComboBox': 'UComboBoxString',
        'QCheckBox': 'UCheckBox',
        'QRadioButton': 'UCheckBox',  # UE5 uses CheckBox for radio
        'QTextEdit': 'UMultiLineEditableTextBox',
        'QProgressBar': 'UProgressBar',
        'QGroupBox': 'UBorder',
        'QSpinBox': 'USpinBox',
        'QDoubleSpinBox': 'USpinBox',
    }
    
    def __init__(self, ui_file_path: str):
        self.ui_file = ui_file_path
        self.tree = ET.parse(ui_file_path)
        self.root = self.tree.getroot()
        self.class_name = ""
        self.widgets = []
    
    def convert_to_ue5(self) -> Dict[str, str]:
        """Convert Qt UI to UE5 widget code"""
        self.class_name = self.root.find(".//class").text if self.root.find(".//class") is not None else "MyWidget"
        self.widgets = self.parse_widgets()
        
        header_code = self.generate_ue5_header()
        cpp_code = self.generate_ue5_cpp()
        
        return {
            'header': header_code,
            'cpp': cpp_code,
            'class_name': self.class_name
        }
    
    def convert_to_python(self) -> str:
        """Convert Qt UI to Python/PyQt code"""
        self.class_name = self.root.find(".//class").text if self.root.find(".//class") is not None else "MyWidget"
        self.widgets = self.parse_widgets()
        
        return self.generate_python_code()
    
    def parse_widgets(self) -> List[Dict]:
        """Parse widgets from Qt UI XML"""
        widgets = []
        
        for widget in self.root.findall(".//widget"):
            widget_info = {
                'class': widget.get('class'),
                'name': widget.get('name'),
                'properties': self._parse_properties(widget)
            }
            widgets.append(widget_info)
        
        return widgets
    
    def _parse_properties(self, widget_element) -> Dict:
        """Parse widget properties"""
        properties = {}
        
        for prop in widget_element.findall(".//property"):
            prop_name = prop.get('name')
            prop_value = None
            
            # Get property value
            string_elem = prop.find('string')
            bool_elem = prop.find('bool')
            number_elem = prop.find('number')
            
            if string_elem is not None:
                prop_value = string_elem.text
            elif bool_elem is not None:
                prop_value = bool_elem.text.lower() == 'true'
            elif number_elem is not None:
                prop_value = number_elem.text
            
            if prop_value is not None:
                properties[prop_name] = prop_value
        
        return properties
    
    def generate_ue5_header(self) -> str:
        """Generate UE5 .h file"""
        header = f"""// {self.class_name}.h
// Auto-generated from Qt Designer .ui file

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"
#include "Components/EditableTextBox.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/ProgressBar.h"
#include "{self.class_name}.generated.h"

UCLASS()
class U{self.class_name} : public UUserWidget
{{
    GENERATED_BODY()

public:
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& MyGeometry, float DeltaTime) override;

protected:
"""
        
        # Add widget properties
        for widget in self.widgets:
            ue5_type = self.WIDGET_MAPPING.get(widget['class'], 'UWidget')
            header += f"    UPROPERTY(meta = (BindWidget))\\n"
            header += f"    {ue5_type}* {widget['name']};\\n\\n"
        
        # Add event handlers
        header += """
private:
    UFUNCTION()
    void OnButtonClicked();
    
    UFUNCTION()
    void OnSliderValueChanged(float Value);
    
    UFUNCTION()
    void OnCheckBoxStateChanged(bool bIsChecked);
}};
"""
        
        return header
    
    def generate_ue5_cpp(self) -> str:
        """Generate UE5 .cpp file"""
        cpp = f"""// {self.class_name}.cpp
// Auto-generated from Qt Designer .ui file

#include "{self.class_name}.h"
#include "Components/Button.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"

void U{self.class_name}::NativeConstruct()
{{
    Super::NativeConstruct();
    
    // Bind button events
"""
        
        # Bind button events
        for widget in self.widgets:
            if 'Button' in widget['class']:
                cpp += f"""    if ({widget['name']})
    {{
        {widget['name']}->OnClicked.AddDynamic(this, &U{self.class_name}::OnButtonClicked);
    }}
    
"""
        
        # Bind slider events
        for widget in self.widgets:
            if 'Slider' in widget['class']:
                cpp += f"""    if ({widget['name']})
    {{
        {widget['name']}->OnValueChanged.AddDynamic(this, &U{self.class_name}::OnSliderValueChanged);
    }}
    
"""
        
        cpp += """}

void U{self.class_name}::NativeTick(const FGeometry& MyGeometry, float DeltaTime)
{{
    Super::NativeTick(MyGeometry, DeltaTime);
    
    // Update UI based on data
    // TODO: Add your update logic here
}}

void U{self.class_name}::OnButtonClicked()
{{
    // Handle button click
    UE_LOG(LogTemp, Warning, TEXT("Button Clicked!"));
    // TODO: Add your button handler logic
}}

void U{self.class_name}::OnSliderValueChanged(float Value)
{{
    // Handle slider change
    UE_LOG(LogTemp, Log, TEXT("Slider Value: %f"), Value);
    // TODO: Add your slider handler logic
}}

void U{self.class_name}::OnCheckBoxStateChanged(bool bIsChecked)
{{
    // Handle checkbox change
    UE_LOG(LogTemp, Log, TEXT("CheckBox State: %d"), bIsChecked);
    // TODO: Add your checkbox handler logic
}}
"""
        
        return cpp.replace("{self.class_name}", self.class_name)
    
    def generate_python_code(self) -> str:
        """Generate Python/PyQt5 code"""
        python = f"""# {self.class_name}.py
# Auto-generated from Qt Designer .ui file

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSlider
from PyQt5.QtCore import Qt, pyqtSignal


class {self.class_name}(QWidget):
    \"\"\"Generated widget from Qt Designer\"\"\"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()
    
    def setupUi(self):
        \"\"\"Setup UI components\"\"\"
        self.layout = QVBoxLayout(self)
        
"""
        
        # Add widgets
        for widget in self.widgets:
            widget_class = widget['class']
            widget_name = widget['name']
            
            python += f"        # {widget_name}\\n"
            python += f"        self.{widget_name} = {widget_class}()\\n"
            
            # Set properties
            if 'text' in widget['properties']:
                python += f"        self.{widget_name}.setText('{widget['properties']['text']}')\\n"
            
            python += f"        self.layout.addWidget(self.{widget_name})\\n\\n"
        
        # Add event connections
        python += "        # Connect signals\\n"
        for widget in self.widgets:
            if 'Button' in widget['class']:
                python += f"        self.{widget['name']}.clicked.connect(self.on_{widget['name']}_clicked)\\n"
            elif 'Slider' in widget['class']:
                python += f"        self.{widget['name']}.valueChanged.connect(self.on_{widget['name']}_changed)\\n"
        
        python += """
    # Event handlers (implement your logic here)
"""
        
        for widget in self.widgets:
            if 'Button' in widget['class']:
                python += f"""    def on_{widget['name']}_clicked(self):
        print("{widget['name']} clicked")
        # TODO: Implement handler
    
"""
            elif 'Slider' in widget['class']:
                python += f"""    def on_{widget['name']}_changed(self, value):
        print(f"{widget['name']} changed: {{value}}")
        # TODO: Implement handler
    
"""
        
        return python


def main():
    parser = argparse.ArgumentParser(description='Convert Qt Designer .ui files to UE5/Python code')
    parser.add_argument('ui_file', help='Path to .ui file')
    parser.add_argument('--output-dir', '-o', default='.', help='Output directory')
    parser.add_argument('--format', '-f', choices=['ue5', 'python'], default='ue5',
                       help='Output format (ue5 or python)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.ui_file):
        print(f"Error: File '{args.ui_file}' not found")
        return 1
    
    converter = QtToUE5Converter(args.ui_file)
    
    if args.format == 'ue5':
        result = converter.convert_to_ue5()
        
        # Write header file
        header_file = os.path.join(args.output_dir, f"{result['class_name']}.h")
        with open(header_file, 'w') as f:
            f.write(result['header'])
        print(f"Generated: {header_file}")
        
        # Write cpp file
        cpp_file = os.path.join(args.output_dir, f"{result['class_name']}.cpp")
        with open(cpp_file, 'w') as f:
            f.write(result['cpp'])
        print(f"Generated: {cpp_file}")
        
    elif args.format == 'python':
        python_code = converter.convert_to_python()
        
        # Write Python file
        python_file = os.path.join(args.output_dir, f"{converter.class_name}.py")
        with open(python_file, 'w') as f:
            f.write(python_code)
        print(f"Generated: {python_file}")
    
    print("Conversion complete!")
    return 0


if __name__ == '__main__':
    exit(main())
