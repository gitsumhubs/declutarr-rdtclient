#!/usr/bin/env python3
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import subprocess
import yaml
import os
import json
from datetime import datetime

app = Flask(__name__)

# Configuration file path
COMPOSE_FILE = '/docker/decluttarr/docker-compose.yml'

# Default settings with descriptions
DEFAULT_SETTINGS = {
    'general': {
        'LOG_LEVEL': {'value': 'INFO', 'type': 'select', 'options': ['INFO', 'VERBOSE'], 'description': 'Logging verbosity level'},
        'TEST_RUN': {'value': 'False', 'type': 'boolean', 'description': 'Dry run mode - shows what would be removed without actually removing'},
        'REMOVE_TIMER': {'value': '6', 'type': 'number', 'description': 'Minutes between cleanup cycles', 'min': 1, 'max': 1440},
    },
    'cleanup_features': {
        'REMOVE_FAILED': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads that failed'},
        'REMOVE_FAILED_IMPORTS': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads that failed to import'},
        'REMOVE_METADATA_MISSING': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads missing metadata'},
        'REMOVE_MISSING_FILES': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads with missing files'},
        'REMOVE_ORPHANS': {'value': 'True', 'type': 'boolean', 'description': 'Remove orphaned downloads not linked to media'},
        'REMOVE_SLOW': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads below minimum speed'},
        'REMOVE_STALLED': {'value': 'True', 'type': 'boolean', 'description': 'Remove stalled downloads'},
        'REMOVE_UNMONITORED': {'value': 'True', 'type': 'boolean', 'description': 'Remove downloads for unmonitored items'},
    },
    'behavior': {
        'MIN_DOWNLOAD_SPEED': {'value': '100', 'type': 'number', 'description': 'Minimum KB/s before considering download "slow"', 'min': 0, 'max': 10000},
        'PERMITTED_ATTEMPTS': {'value': '3', 'type': 'number', 'description': 'Times to detect issue before removal', 'min': 1, 'max': 10},
        'IGNORE_PRIVATE_TRACKERS': {'value': 'False', 'type': 'boolean', 'description': 'Skip downloads from private trackers'},
        'NO_STALLED_REMOVAL_QBIT_TAG': {'value': "Don't Kill", 'type': 'text', 'description': 'qBittorrent tag to protect from stalled removal'},
    },
    'arr_services': {
        'RADARR_URL': {'value': 'http://192.168.1.4:7878', 'type': 'text', 'description': 'Radarr base URL'},
        'RADARR_KEY': {'value': '', 'type': 'password', 'description': 'Radarr API key'},
        'SONARR_URL': {'value': 'http://192.168.1.4:8989', 'type': 'text', 'description': 'Sonarr base URL'},
        'SONARR_KEY': {'value': '', 'type': 'password', 'description': 'Sonarr API key'},
        'LIDARR_URL': {'value': '', 'type': 'text', 'description': 'Lidarr base URL (optional)'},
        'LIDARR_KEY': {'value': '', 'type': 'password', 'description': 'Lidarr API key (optional)'},
        'READARR_URL': {'value': '', 'type': 'text', 'description': 'Readarr base URL (optional)'},
        'READARR_KEY': {'value': '', 'type': 'password', 'description': 'Readarr API key (optional)'},
    },
    'download_client': {
        'QBITTORRENT_URL': {'value': '', 'type': 'text', 'description': 'qBittorrent base URL (optional)'},
        'QBITTORRENT_USERNAME': {'value': '', 'type': 'text', 'description': 'qBittorrent username (optional)'},
        'QBITTORRENT_PASSWORD': {'value': '', 'type': 'password', 'description': 'qBittorrent password (optional)'},
    }
}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Decluttarr Manager</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; 
            color: #e6edf3; 
            margin: 0; 
            padding: 20px; 
            line-height: 1.5;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: #161b22; 
            padding: 30px; 
            border-radius: 12px; 
            margin-bottom: 30px;
            text-align: center;
            border: 1px solid #30363d;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        .header h1 { margin: 0 0 10px 0; color: #f0f6fc; font-size: 2.5rem; }
        .header p { margin: 0; color: #8b949e; font-size: 1.1rem; }
        
        .status-bar {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }
        .status-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #f85149;
        }
        .status-indicator.running { background: #3fb950; }
        
        .tabs {
            display: flex;
            background: #161b22;
            border-radius: 8px 8px 0 0;
            border: 1px solid #30363d;
            border-bottom: none;
            overflow-x: auto;
        }
        .tab {
            padding: 15px 25px;
            cursor: pointer;
            border-right: 1px solid #30363d;
            background: #161b22;
            color: #8b949e;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .tab:hover { background: #21262d; color: #e6edf3; }
        .tab.active { background: #0d1117; color: #f0f6fc; border-bottom: 2px solid #2f81f7; }
        .tab:last-child { border-right: none; }
        
        .tab-content {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 0 0 8px 8px;
            padding: 30px;
            margin-bottom: 30px;
        }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }
        
        .section-title {
            font-size: 1.5rem;
            margin: 0 0 20px 0;
            color: #f0f6fc;
            border-bottom: 2px solid #30363d;
            padding-bottom: 10px;
        }
        
        .form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 25px;
        }
        
        .form-group {
            background: #0d1117;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #30363d;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #f0f6fc;
        }
        .form-group .description {
            font-size: 0.9rem;
            color: #8b949e;
            margin-bottom: 10px;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 1px solid #30363d;
            border-radius: 6px;
            background: #0d1117;
            color: #e6edf3;
            font-size: 14px;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #2f81f7;
            box-shadow: 0 0 0 2px rgba(47, 129, 247, 0.2);
        }
        
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .checkbox-group input[type="checkbox"] {
            width: auto;
            margin: 0;
        }
        
        .button-group {
            display: flex;
            gap: 15px;
            justify-content: center;
            margin-top: 30px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .btn-primary { background: #2f81f7; color: white; }
        .btn-primary:hover { background: #1f6feb; }
        .btn-success { background: #238636; color: white; }
        .btn-success:hover { background: #2ea043; }
        .btn-warning { background: #bf8700; color: white; }
        .btn-warning:hover { background: #d29922; }
        .btn-danger { background: #da3633; color: white; }
        .btn-danger:hover { background: #f85149; }
        .btn-secondary { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        
        .logs-container {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 8px;
            height: 400px;
            overflow-y: auto;
            padding: 20px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.4;
            white-space: pre-wrap;
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid;
        }
        .alert-success { 
            background: rgba(35, 134, 54, 0.15); 
            border-color: #238636; 
            color: #3fb950; 
        }
        .alert-error { 
            background: rgba(248, 81, 73, 0.15); 
            border-color: #f85149; 
            color: #f85149; 
        }
        .alert-warning { 
            background: rgba(210, 153, 34, 0.15); 
            border-color: #d29922; 
            color: #d29922; 
        }
        
        @media (max-width: 768px) {
            .form-grid { grid-template-columns: 1fr; }
            .button-group { flex-direction: column; }
            .status-bar { flex-direction: column; align-items: stretch; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚙️ Decluttarr Manager</h1>
            <p>Interactive configuration and management interface</p>
        </div>
        
        <div class="status-bar">
            <div class="status-item">
                <div class="status-indicator" id="containerStatus"></div>
                <span id="statusText">Checking status...</span>
            </div>
            <div class="status-item">
                <strong>Last Updated:</strong>
                <span id="lastUpdate">Never</span>
            </div>
        </div>
        
        {% if message %}
        <div class="alert alert-{{ message.type }}">
            {{ message.text }}
        </div>
        {% endif %}
        
        <div class="tabs">
            <div class="tab active" onclick="switchTab('settings')">📋 Settings</div>
            <div class="tab" onclick="switchTab('logs')">📄 Live Logs</div>
            <div class="tab" onclick="switchTab('actions')">🔧 Actions</div>
        </div>
        
        <div class="tab-content">
            <!-- Settings Tab -->
            <div class="tab-pane active" id="settings">
                <form method="POST" action="/save-settings">
                    {% for category, settings in config.items() %}
                    <div class="section-title">
                        {% if category == 'general' %}🔧 General Settings
                        {% elif category == 'cleanup_features' %}🧹 Cleanup Features
                        {% elif category == 'behavior' %}⚡ Behavior Settings
                        {% elif category == 'arr_services' %}🎬 *arr Services
                        {% elif category == 'download_client' %}⬇️ Download Client
                        {% endif %}
                    </div>
                    
                    <div class="form-grid">
                        {% for key, setting in settings.items() %}
                        <div class="form-group">
                            <label for="{{ key }}">{{ key.replace('_', ' ').title() }}</label>
                            <div class="description">{{ setting.description }}</div>
                            
                            {% if setting.type == 'boolean' %}
                            <div class="checkbox-group">
                                <input type="checkbox" id="{{ key }}" name="{{ key }}" 
                                       {% if setting.value == 'True' %}checked{% endif %}>
                                <label for="{{ key }}">Enable</label>
                            </div>
                            {% elif setting.type == 'select' %}
                            <select id="{{ key }}" name="{{ key }}">
                                {% for option in setting.options %}
                                <option value="{{ option }}" 
                                        {% if option == setting.value %}selected{% endif %}>
                                    {{ option }}
                                </option>
                                {% endfor %}
                            </select>
                            {% elif setting.type == 'number' %}
                            <input type="number" id="{{ key }}" name="{{ key }}" 
                                   value="{{ setting.value }}"
                                   {% if setting.min %}min="{{ setting.min }}"{% endif %}
                                   {% if setting.max %}max="{{ setting.max }}"{% endif %}>
                            {% elif setting.type == 'password' %}
                            <input type="password" id="{{ key }}" name="{{ key }}" 
                                   value="{{ setting.value }}" placeholder="Enter {{ key.replace('_', ' ').lower() }}">
                            {% else %}
                            <input type="text" id="{{ key }}" name="{{ key }}" 
                                   value="{{ setting.value }}" placeholder="Enter {{ key.replace('_', ' ').lower() }}">
                            {% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    {% endfor %}
                    
                    <div class="button-group">
                        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
                        <button type="button" class="btn btn-secondary" onclick="resetForm()">🔄 Reset</button>
                    </div>
                </form>
            </div>
            
            <!-- Logs Tab -->
            <div class="tab-pane" id="logs">
                <div class="section-title">📄 Live Container Logs</div>
                <div class="button-group" style="margin-bottom: 20px;">
                    <button class="btn btn-primary" onclick="refreshLogs()">🔄 Refresh Logs</button>
                    <button class="btn btn-secondary" onclick="clearLogDisplay()">🗑️ Clear Display</button>
                </div>
                <div class="logs-container" id="logsContainer">
                    Click "Refresh Logs" to load container logs...
                </div>
            </div>
            
            <!-- Actions Tab -->
            <div class="tab-pane" id="actions">
                <div class="section-title">🔧 Container Actions</div>
                
                <div class="form-grid">
                    <div class="form-group">
                        <h3>Container Management</h3>
                        <div class="description">Control the decluttarr container</div>
                        <div class="button-group" style="margin-top: 15px;">
                            <button class="btn btn-success" onclick="startContainer()">▶️ Start</button>
                            <button class="btn btn-warning" onclick="restartContainer()">♻️ Quick Restart</button>
                            <button class="btn btn-primary" onclick="restartWithSettings()">🔄 Restart & Apply Settings</button>
                            <button class="btn btn-danger" onclick="stopContainer()">⏹️ Stop</button>
                        </div>
                        <div style="margin-top: 10px; font-size: 0.9rem; color: #8b949e;">
                            <strong>Note:</strong> Use "Restart & Apply Settings" after changing configuration to ensure environment variables are updated.
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <h3>Test Configuration</h3>
                        <div class="description">Test your *arr service connections</div>
                        <div class="button-group" style="margin-top: 15px;">
                            <button class="btn btn-primary" onclick="testConnections()">🔍 Test Connections</button>
                        </div>
                        <div id="testResults" style="margin-top: 15px;"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabName) {
            // Hide all tab panes
            document.querySelectorAll('.tab-pane').forEach(pane => {
                pane.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab pane
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
        }

        function resetForm() {
            if (confirm('Are you sure you want to reset all settings to their current saved values?')) {
                location.reload();
            }
        }

        async function refreshLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                const logsContainer = document.getElementById('logsContainer');
                
                if (data.logs && data.logs.length > 0) {
                    // Format logs with proper timestamps and colors
                    const formattedLogs = data.logs.map(line => {
                        // Extract Docker timestamp if present
                        const timestampMatch = line.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(.*)$/);
                        if (timestampMatch) {
                            const rawTimestamp = timestampMatch[1];
                            const logContent = timestampMatch[2];
                            const date = new Date(rawTimestamp);
                            const formattedTime = date.toLocaleString();
                            return `[${formattedTime}] ${logContent}`;
                        }
                        return line;
                    }).join('\n');
                    
                    logsContainer.textContent = formattedLogs;
                } else {
                    logsContainer.textContent = 'No logs available or container not running.';
                }
                
                logsContainer.scrollTop = logsContainer.scrollHeight;
                updateStatus(data.status);
            } catch (error) {
                document.getElementById('logsContainer').textContent = 'Error fetching logs: ' + error.message;
            }
        }

        function clearLogDisplay() {
            document.getElementById('logsContainer').textContent = 'Logs cleared. Click "Refresh Logs" to reload.';
        }

        async function startContainer() {
            await containerAction('start', 'Starting container...');
        }

        async function restartContainer() {
            if (confirm('Are you sure you want to restart the decluttarr container?\\n\\nNote: This is a quick restart and may not apply new environment variable changes.')) {
                await containerAction('restart', 'Restarting container...');
            }
        }

        async function restartWithSettings() {
            if (confirm('Are you sure you want to restart the decluttarr container with settings applied?\\n\\nThis will recreate the container to ensure all environment variables are updated.')) {
                try {
                    const response = await fetch('/api/container/restart-with-settings', { method: 'POST' });
                    const data = await response.json();
                    alert(data.message);
                    setTimeout(checkStatus, 3000);
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }
        }

        async function stopContainer() {
            if (confirm('Are you sure you want to stop the decluttarr container?')) {
                await containerAction('stop', 'Stopping container...');
            }
        }

        async function containerAction(action, message) {
            try {
                const response = await fetch(`/api/container/${action}`, { method: 'POST' });
                const data = await response.json();
                alert(data.message || message);
                setTimeout(checkStatus, 2000);
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function testConnections() {
            const testResults = document.getElementById('testResults');
            testResults.innerHTML = '<div class="alert alert-warning">Testing connections...</div>';
            
            try {
                const response = await fetch('/api/test-connections');
                const data = await response.json();
                
                let html = '';
                for (const [service, result] of Object.entries(data)) {
                    const status = result.success ? 'success' : 'error';
                    html += `<div class="alert alert-${status}">
                        <strong>${service}:</strong> ${result.message}
                    </div>`;
                }
                testResults.innerHTML = html;
            } catch (error) {
                testResults.innerHTML = `<div class="alert alert-error">Error testing connections: ${error.message}</div>`;
            }
        }

        async function checkStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateStatus(data.status);
            } catch (error) {
                console.error('Error checking status:', error);
            }
        }

        function updateStatus(status) {
            const indicator = document.getElementById('containerStatus');
            const statusText = document.getElementById('statusText');
            const lastUpdate = document.getElementById('lastUpdate');
            
            if (status === 'running') {
                indicator.classList.add('running');
                statusText.textContent = 'Container Running';
            } else {
                indicator.classList.remove('running');
                statusText.textContent = 'Container Stopped';
            }
            
            lastUpdate.textContent = new Date().toLocaleTimeString();
        }

        // Initialize
        checkStatus();
        setInterval(checkStatus, 30000); // Check status every 30 seconds
    </script>
</body>
</html>
'''

def load_current_settings():
    """Load current settings from docker-compose.yml"""
    try:
        with open(COMPOSE_FILE, 'r') as f:
            compose_data = yaml.safe_load(f)
        
        if 'services' in compose_data and 'decluttarr' in compose_data['services']:
            env_vars = compose_data['services']['decluttarr'].get('environment', [])
            current_settings = {}
            
            # Parse environment variables
            for env_var in env_vars:
                if '=' in env_var:
                    key, value = env_var.split('=', 1)
                    current_settings[key] = value
            
            # Update default settings with current values
            for category in DEFAULT_SETTINGS:
                for key in DEFAULT_SETTINGS[category]:
                    if key in current_settings:
                        DEFAULT_SETTINGS[category][key]['value'] = current_settings[key]
        
        return DEFAULT_SETTINGS
    except Exception as e:
        print(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS

def save_settings_to_compose(settings_data):
    """Save settings to docker-compose.yml"""
    try:
        with open(COMPOSE_FILE, 'r') as f:
            compose_data = yaml.safe_load(f)
        
        # Build environment variables list
        env_vars = [
            'TZ=America/Detroit',
            'PUID=1000',
            'PGID=1000'
        ]
        
        for category in DEFAULT_SETTINGS:
            for key in DEFAULT_SETTINGS[category]:
                if key in settings_data:
                    value = settings_data[key]
                    # Convert checkbox values
                    if key in settings_data and isinstance(settings_data[key], list):
                        value = 'True'
                    elif DEFAULT_SETTINGS[category][key]['type'] == 'boolean' and key not in settings_data:
                        value = 'False'
                    
                    # Only add non-empty values
                    if value and value.strip():
                        env_vars.append(f"{key}={value}")
        
        # Update compose file
        compose_data['services']['decluttarr']['environment'] = env_vars
        
        with open(COMPOSE_FILE, 'w') as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

@app.route('/')
def home():
    config = load_current_settings()
    message = request.args.get('message')
    message_type = request.args.get('type', 'success')
    
    return render_template_string(HTML_TEMPLATE, 
                                config=config, 
                                message={'text': message, 'type': message_type} if message else None)

@app.route('/save-settings', methods=['POST'])
def save_settings():
    try:
        settings_data = request.form.to_dict(flat=False)
        
        # Convert form data to flat dict
        flat_settings = {}
        for key, value_list in settings_data.items():
            if isinstance(value_list, list):
                value = value_list[0] if len(value_list) == 1 else 'True'
                # Convert HTML checkbox values to proper boolean strings
                if value == 'on':
                    value = 'True'
                flat_settings[key] = value
            else:
                # Convert HTML checkbox values to proper boolean strings
                value = 'True' if value_list == 'on' else value_list
                flat_settings[key] = value
        
        # Handle unchecked checkboxes (they don't appear in form data)
        checkbox_fields = [
            'REMOVE_FAILED', 'REMOVE_FAILED_IMPORTS', 'REMOVE_METADATA_MISSING',
            'REMOVE_MISSING_FILES', 'REMOVE_ORPHANS', 'REMOVE_SLOW', 
            'REMOVE_STALLED', 'REMOVE_UNMONITORED', 'IGNORE_PRIVATE_TRACKERS'
        ]
        for field in checkbox_fields:
            if field not in flat_settings:
                flat_settings[field] = 'False'
        
        if save_settings_to_compose(flat_settings):
            return redirect(url_for('home', message='Settings saved successfully! Use the Actions tab to restart and apply changes.', type='success'))
        else:
            return redirect(url_for('home', message='Error saving settings. Please try again.', type='error'))
    except Exception as e:
        return redirect(url_for('home', message=f'Error: {str(e)}', type='error'))

@app.route('/api/container/restart-with-settings', methods=['POST'])
def restart_with_settings():
    """Restart container after settings change - forces recreation to load new environment variables"""
    try:
        # Stop the container
        subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'stop', 'decluttarr'], 
                     timeout=30, check=True, cwd='/docker/decluttarr')
        
        # Remove the container to force recreation
        subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'rm', '-f', 'decluttarr'], 
                     timeout=30, check=True, cwd='/docker/decluttarr')
        
        # Start with new settings
        subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'up', '-d', 'decluttarr'], 
                     timeout=60, check=True, cwd='/docker/decluttarr')
        
        return jsonify({'message': 'Container recreated successfully with new settings!'})
    except subprocess.CalledProcessError as e:
        return jsonify({'message': f'Docker compose error: {str(e)}'}, 500)
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}, 500)

@app.route('/api/logs')
def get_logs():
    try:
        # Get logs with timestamps from last 24 hours
        result = subprocess.run(['docker', 'logs', '--timestamps', '--since', '24h', 'decluttarr'], 
                              capture_output=True, text=True, timeout=30)
        
        logs = []
        # Docker logs can come from both stdout and stderr
        if result.stderr:
            logs.extend(result.stderr.split('\n'))
        if result.stdout:
            logs.extend(result.stdout.split('\n'))
        
        logs = [log.strip() for log in logs if log.strip()]
        
        # Check status
        status_result = subprocess.run(['docker', 'ps', '--filter', 'name=decluttarr', '--format', '{{.Status}}'], 
                                     capture_output=True, text=True, timeout=5)
        status = 'running' if 'Up' in status_result.stdout else 'stopped'
        
        return jsonify({'logs': logs, 'status': status})
    except Exception as e:
        return jsonify({'logs': [f'Error: {str(e)}'], 'status': 'unknown'})

@app.route('/api/status')
def get_status():
    try:
        result = subprocess.run(['docker', 'ps', '--filter', 'name=decluttarr', '--format', '{{.Status}}'], 
                              capture_output=True, text=True, timeout=5)
        status = 'running' if 'Up' in result.stdout else 'stopped'
        return jsonify({'status': status})
    except Exception as e:
        return jsonify({'status': 'unknown', 'error': str(e)})

@app.route('/api/container/<action>', methods=['POST'])
def container_action(action):
    try:
        if action == 'start':
            # Use compose up to ensure container is created with latest environment
            subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'up', '-d', 'decluttarr'], 
                         timeout=60, check=True, cwd='/docker/decluttarr')
            return jsonify({'message': 'Container started successfully (with latest settings)'})
        elif action == 'stop':
            subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'stop', 'decluttarr'], 
                         timeout=30, check=True, cwd='/docker/decluttarr')
            return jsonify({'message': 'Container stopped successfully'})
        elif action == 'restart':
            # Use compose down/up to force recreation with new environment variables
            subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'stop', 'decluttarr'], 
                         timeout=30, check=True, cwd='/docker/decluttarr')
            subprocess.run(['docker', 'compose', '-f', '/docker/decluttarr/docker-compose.yml', 'up', '-d', 'decluttarr'], 
                         timeout=60, check=True, cwd='/docker/decluttarr')
            return jsonify({'message': 'Container restarted successfully (settings applied)'})
        else:
            return jsonify({'message': 'Invalid action'}, 400)
    except subprocess.CalledProcessError as e:
        return jsonify({'message': f'Docker compose error: {str(e)}'}, 500)
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}, 500)

@app.route('/api/test-connections')
def test_connections():
    config = load_current_settings()
    results = {}
    
    # Test each *arr service
    for service in ['RADARR', 'SONARR', 'LIDARR', 'READARR']:
        url_key = f"{service}_URL"
        key_key = f"{service}_KEY"
        
        url = config['arr_services'].get(url_key, {}).get('value', '').strip()
        api_key = config['arr_services'].get(key_key, {}).get('value', '').strip()
        
        if url and api_key:
            try:
                import requests
                test_url = f"{url.rstrip('/')}/api/v3/system/status" if service in ['RADARR', 'SONARR'] else f"{url.rstrip('/')}/api/v1/system/status"
                response = requests.get(test_url, headers={'X-Api-Key': api_key}, timeout=10)
                
                if response.status_code == 200:
                    results[service] = {'success': True, 'message': 'Connection successful'}
                else:
                    results[service] = {'success': False, 'message': f'HTTP {response.status_code}'}
            except Exception as e:
                results[service] = {'success': False, 'message': str(e)}
        elif url:
            results[service] = {'success': False, 'message': 'API key missing'}
        else:
            results[service] = {'success': False, 'message': 'URL not configured'}
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=False)