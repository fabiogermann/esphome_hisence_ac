#!/bin/bash

# Hisense AC ESPHome Configuration Validator
# This script validates the ESPHome configuration before compilation
# Usage: ./validate_config.sh [config_file]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration file
CONFIG_FILE="${1:-hisense_ac_modern.yaml}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Function to print colored output
print_status() {
    echo -e "${2}${1}${NC}"
}

print_error() {
    echo -e "${RED}✗ ${1}${NC}"
}

print_success() {
    echo -e "${GREEN}✓ ${1}${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ ${1}${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ ${1}${NC}"
}

# Header
echo "================================================"
echo "   Hisense AC ESPHome Configuration Validator"
echo "================================================"
echo ""

# Check if running from correct directory
if [ ! -f "$CONFIG_FILE" ]; then
    print_error "Configuration file '$CONFIG_FILE' not found!"
    print_info "Please run this script from the modern_hisense_ac directory"
    print_info "Or specify the configuration file: ./validate_config.sh <config_file>"
    exit 1
fi

print_info "Validating configuration: $CONFIG_FILE"
echo ""

# Step 1: Check if ESPHome is installed
echo "Step 1: Checking ESPHome installation..."
if command -v esphome &> /dev/null; then
    ESPHOME_VERSION=$(esphome version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    print_success "ESPHome is installed (version: $ESPHOME_VERSION)"
    
    # Check version compatibility
    MIN_VERSION="2023.8.0"
    if [ "$(printf '%s\n' "$MIN_VERSION" "$ESPHOME_VERSION" | sort -V | head -n1)" = "$MIN_VERSION" ]; then
        print_success "ESPHome version is compatible"
    else
        print_warning "ESPHome version might be too old. Recommended: $MIN_VERSION or newer"
    fi
else
    print_error "ESPHome is not installed!"
    echo ""
    print_info "Installation instructions:"
    print_info "  Using pip:    pip install esphome"
    print_info "  Using Docker: docker pull esphome/esphome"
    print_info "  Using brew:   brew install esphome"
    exit 1
fi
echo ""

# Step 2: Check for required files
echo "Step 2: Checking required files..."
REQUIRED_FILES=(
    "hisense_ac_modern.h"
    "secrets.yaml.example"
)

MISSING_FILES=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        print_success "Found: $file"
    else
        print_error "Missing: $file"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    print_error "Missing $MISSING_FILES required file(s)"
    exit 1
fi
echo ""

# Step 3: Check for secrets.yaml
echo "Step 3: Checking secrets configuration..."
if [ -f "secrets.yaml" ]; then
    print_success "Found secrets.yaml"
    
    # Check for required secrets
    REQUIRED_SECRETS=(
        "wifi_ssid"
        "wifi_password"
        "api_password"
        "ota_password"
    )
    
    MISSING_SECRETS=0
    for secret in "${REQUIRED_SECRETS[@]}"; do
        if grep -q "^${secret}:" secrets.yaml 2>/dev/null; then
            # Check if it's not a placeholder
            VALUE=$(grep "^${secret}:" secrets.yaml | cut -d'"' -f2)
            if [[ "$VALUE" == *"Your"* ]] || [[ "$VALUE" == *"your"* ]] || [[ "$VALUE" == *"CHANGE"* ]]; then
                print_warning "Secret '$secret' appears to be a placeholder: '$VALUE'"
                MISSING_SECRETS=$((MISSING_SECRETS + 1))
            else
                print_success "Secret configured: $secret"
            fi
        else
            print_error "Missing secret: $secret"
            MISSING_SECRETS=$((MISSING_SECRETS + 1))
        fi
    done
    
    if [ $MISSING_SECRETS -gt 0 ]; then
        print_warning "Please update $MISSING_SECRETS secret(s) in secrets.yaml"
    fi
else
    print_error "secrets.yaml not found!"
    print_info "Creating from template..."
    cp secrets.yaml.example secrets.yaml
    print_success "Created secrets.yaml from template"
    print_warning "Please edit secrets.yaml with your network credentials"
    exit 1
fi
echo ""

# Step 4: Validate YAML syntax
echo "Step 4: Validating YAML syntax..."
if command -v python3 &> /dev/null; then
    python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_FILE', 'r') as f:
        yaml.safe_load(f)
    print('YAML syntax is valid')
    sys.exit(0)
except yaml.YAMLError as e:
    print(f'YAML syntax error: {e}')
    sys.exit(1)
" && print_success "YAML syntax is valid" || print_error "YAML syntax error detected"
else
    print_warning "Python3 not found, skipping YAML syntax check"
fi
echo ""

# Step 5: Check configuration with ESPHome
echo "Step 5: Running ESPHome configuration check..."
if esphome config "$CONFIG_FILE" > /tmp/esphome_validate.log 2>&1; then
    print_success "ESPHome configuration is valid!"
    
    # Extract some useful information
    echo ""
    print_info "Configuration details:"
    grep -E "name:|platform:|board:" /tmp/esphome_validate.log | head -5 | while read -r line; do
        print_info "  $line"
    done
else
    print_error "ESPHome configuration validation failed!"
    echo ""
    print_info "Error details:"
    tail -20 /tmp/esphome_validate.log | while IFS= read -r line; do
        echo "  $line"
    done
    exit 1
fi
echo ""

# Step 6: Check for board-specific configuration
echo "Step 6: Checking board compatibility..."
if grep -q "esp32:" "$CONFIG_FILE"; then
    BOARD_TYPE="ESP32"
    print_info "Configuration is for ESP32"
    
    # Check if user might need ESP8266 variant
    if grep -q "board:.*esp8266" "$CONFIG_FILE"; then
        print_warning "Mismatch: ESP32 platform with ESP8266 board specified"
        print_info "Consider using esp8266_variant.yaml instead"
    fi
elif grep -q "esp8266:" "$CONFIG_FILE"; then
    BOARD_TYPE="ESP8266"
    print_info "Configuration is for ESP8266"
    print_warning "ESP8266 has limited memory. Consider ESP32 for better performance"
else
    print_error "No board platform specified!"
    exit 1
fi
echo ""

# Step 7: Dry-run compile (optional)
echo "Step 7: Dry-run compilation check..."
read -p "Do you want to perform a dry-run compilation? This may take a few minutes. (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting dry-run compilation..."
    
    # Create a temporary directory for build files
    BUILD_DIR="/tmp/esphome_build_$$"
    mkdir -p "$BUILD_DIR"
    
    if esphome compile "$CONFIG_FILE" --only-generate 2>&1 | tee /tmp/esphome_compile.log | grep -E "ERROR|WARNING|INFO"; then
        # Check if compilation was successful
        if grep -q "ERROR" /tmp/esphome_compile.log; then
            print_error "Compilation errors detected!"
            echo ""
            print_info "Error summary:"
            grep "ERROR" /tmp/esphome_compile.log | head -10 | while IFS= read -r line; do
                echo "  $line"
            done
            exit 1
        else
            print_success "Dry-run compilation successful!"
            
            # Check memory usage for ESP8266
            if [ "$BOARD_TYPE" = "ESP8266" ]; then
                if grep -q "RAM:" /tmp/esphome_compile.log; then
                    print_info "Memory usage:"
                    grep -E "RAM:|Flash:" /tmp/esphome_compile.log | while IFS= read -r line; do
                        print_info "  $line"
                    done
                fi
            fi
        fi
    else
        print_error "Compilation failed!"
        exit 1
    fi
    
    # Cleanup
    rm -rf "$BUILD_DIR"
else
    print_info "Skipping dry-run compilation"
fi
echo ""

# Step 8: Check for common issues
echo "Step 8: Checking for common issues..."
ISSUES_FOUND=0

# Check UART pins
if grep -q "tx_pin:.*GPIO1" "$CONFIG_FILE" && grep -q "rx_pin:.*GPIO3" "$CONFIG_FILE"; then
    print_success "Standard UART pins configured (GPIO1/GPIO3)"
else
    print_warning "Non-standard UART pins detected. Verify your wiring!"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Check baud rate
if grep -q "baud_rate:.*9600" "$CONFIG_FILE"; then
    print_success "Correct baud rate (9600) configured"
else
    print_warning "Non-standard baud rate. Most Hisense AC units use 9600"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Check for logger conflicts with UART
if grep -q "logger:" "$CONFIG_FILE"; then
    if grep -q "baud_rate:.*0" "$CONFIG_FILE"; then
        print_success "Logger configured to not interfere with UART"
    else
        print_warning "Logger might interfere with UART communication"
        print_info "Consider setting logger baud_rate to 0 or using hardware_uart"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
fi

if [ $ISSUES_FOUND -eq 0 ]; then
    print_success "No common issues detected"
fi
echo ""

# Final summary
echo "================================================"
echo "              Validation Summary"
echo "================================================"
echo ""

if [ $MISSING_FILES -eq 0 ] && [ ${MISSING_SECRETS:-0} -eq 0 ] && [ $ISSUES_FOUND -eq 0 ]; then
    print_success "Configuration is ready for deployment!"
    echo ""
    print_info "Next steps:"
    print_info "1. Connect your ESP device via USB"
    print_info "2. Run: esphome run $CONFIG_FILE"
    print_info "3. Monitor logs: esphome logs $CONFIG_FILE"
    echo ""
    print_info "For detailed testing instructions, see TESTING_GUIDE.md"
else
    print_warning "Configuration needs attention before deployment"
    echo ""
    if [ $MISSING_FILES -gt 0 ]; then
        print_info "• Fix missing files"
    fi
    if [ ${MISSING_SECRETS:-0} -gt 0 ]; then
        print_info "• Update secrets in secrets.yaml"
    fi
    if [ $ISSUES_FOUND -gt 0 ]; then
        print_info "• Review warnings above"
    fi
    echo ""
    print_info "Run this script again after making changes"
fi

echo ""
print_info "For more help, see:"
print_info "• TESTING_GUIDE.md - Complete testing procedures"
print_info "• MIGRATION_GUIDE.md - Migrating from old configurations"
print_info "• README.md - General setup and usage"

# Cleanup temporary files
rm -f /tmp/esphome_validate.log /tmp/esphome_compile.log 2>/dev/null

exit 0