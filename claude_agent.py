import asyncio
import json
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ToolUseBlock, TextBlock, ResultMessage, create_sdk_mcp_server, tool
import subprocess
import os
from pathlib import Path

async def main():
    # Skills and CLAUDE.md are loaded automatically by Claude SDK from cwd
    # No manual instruction loading needed - the SDK reads:
    # - /home/user/app/CLAUDE.md (copied from SANDBOX_PROMPT.md)
    # - /home/user/app/.claude/skills/ (copied from sandbox_skills/)

    # ============================================================
    # HELPER: Sort apps by dependencies for LivingApps creation
    # ============================================================
    def sort_apps_by_dependencies(apps):
        """Sort apps so those without applookup dependencies come first."""
        dependencies = {}
        app_map = {}
        
        for app in apps:
            identifier = app["identifier"]
            app_map[identifier] = app
            dependencies[identifier] = set()
            
            for ctrl in app.get("controls", {}).values():
                if "applookup" in ctrl.get("fulltype", ""):
                    ref = ctrl.get("lookup_app_ref")
                    if ref:
                        dependencies[identifier].add(ref)
        
        # Topological sort (Kahn's algorithm)
        sorted_apps = []
        in_degree = {app_id: len(deps) for app_id, deps in dependencies.items()}
        queue = [app_id for app_id, degree in in_degree.items() if degree == 0]
        
        while queue:
            current = queue.pop(0)
            if current in app_map:
                sorted_apps.append(app_map[current])
            
            for app_id, deps in dependencies.items():
                if current in deps:
                    in_degree[app_id] -= 1
                    if in_degree[app_id] == 0:
                        queue.append(app_id)
        
        return sorted_apps if len(sorted_apps) == len(apps) else apps

    def run_git_cmd(cmd: str):
        """Executes a Git command and throws an error on failure"""
        print(f"[DEPLOY] Executing: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            cwd="/home/user/app",
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise Exception(f"Git Error ({cmd}): {result.stderr}")
        return result.stdout

    @tool("deploy_to_github",
    "Initializes Git, commits EVERYTHING, and pushes it to the configured repository. Use this ONLY at the very end.",
    {})
    async def deploy_to_github(args):
        import time
        t_deploy_start = time.time()
        try:
            run_git_cmd("git config --global user.email 'lilo@livinglogic.de'")
            run_git_cmd("git config --global user.name 'Lilo'")
            
            git_push_url = os.getenv('GIT_PUSH_URL')
            appgroup_id = os.getenv('REPO_NAME')
            livingapps_api_key = os.getenv('LIVINGAPPS_API_KEY')
            
            # Prüfe ob Repo existiert und übernehme .git History
            print("[DEPLOY] Prüfe ob Repo bereits existiert...")
            try:
                run_git_cmd(f"git clone --depth 1 {git_push_url} /tmp/old_repo")
                run_git_cmd("cp -r /tmp/old_repo/.git /home/user/app/.git")
                print("[DEPLOY] ✅ History vom existierenden Repo übernommen")
            except:
                # Neues Repo - von vorne initialisieren
                print("[DEPLOY] ✅ Neues Repo wird initialisiert")
                run_git_cmd("git init")
                run_git_cmd("git checkout -b main")
                run_git_cmd(f"git remote add origin {git_push_url}")
            
            # Mit HOME=/home/user/app schreibt das SDK direkt nach /home/user/app/.claude/
            # Kein Kopieren nötig! .claude ist bereits im Repo-Ordner.
            print("[DEPLOY] 💾 Session wird mit Code gepusht (HOME=/home/user/app)")
            
            # Session ID wird später von ResultMessage gespeichert
            # Hier nur prüfen ob .claude existiert
            check_result = subprocess.run(
                "ls /home/user/app/.claude 2>&1",
                shell=True,
                capture_output=True,
                text=True
            )
            if check_result.returncode == 0:
                print("[DEPLOY] ✅ .claude/ vorhanden - wird mit gepusht")
            else:
                print("[DEPLOY] ⚠️ .claude/ nicht gefunden")
            
            # Neuen Code committen (includes .claude/ direkt im Repo)
            run_git_cmd("git add -A")
            # Force add .claude (exclude debug/ - may contain secrets)
            subprocess.run("git add -f .claude ':!.claude/debug' .claude_session_id 2>/dev/null", shell=True, cwd="/home/user/app")
            run_git_cmd("git commit -m 'Lilo Auto-Deploy' --allow-empty")
            run_git_cmd("git push origin main")
            
            t_push_done = time.time()
            print(f"[DEPLOY] ✅ Push erfolgreich! ({t_push_done - t_deploy_start:.1f}s)")
            
            # Ab hier: Warte auf Dashboard und aktiviere Links
            if livingapps_api_key and appgroup_id:
                import httpx
                t_links_start = time.time()
                
                headers = {
                    "X-API-Key": livingapps_api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                try:
                    # 1. Hole alle App-IDs der Appgroup
                    print(f"[DEPLOY] Lade Appgroup: {appgroup_id}")
                    resp = httpx.get(
                        f"https://my.living-apps.de/rest/appgroups/{appgroup_id}",
                        headers=headers,
                        timeout=30
                    )
                    resp.raise_for_status()
                    appgroup = resp.json()
                    
                    app_ids = [app_data["id"] for app_data in appgroup.get("apps", {}).values()]
                    print(f"[DEPLOY] Gefunden: {len(app_ids)} Apps")
                    
                    if not app_ids:
                        print("[DEPLOY] ⚠️ Keine Apps gefunden")
                        return {"content": [{"type": "text", "text": "✅ Deployment erfolgreich!"}]}
                    
                    dashboard_url = f"https://my.living-apps.de/github/{appgroup_id}/"
                    
                    # 2. Warte bis Dashboard verfügbar ist
                    print(f"[DEPLOY] ⏳ Warte auf Dashboard: {dashboard_url}")
                    max_attempts = 180  # Max 180 Sekunden warten
                    for attempt in range(max_attempts):
                        try:
                            check_resp = httpx.get(dashboard_url, timeout=5)
                            if check_resp.status_code == 200:
                                print(f"[DEPLOY] ✅ Dashboard ist verfügbar!")
                                break
                        except:
                            pass
                        
                        if attempt < max_attempts - 1:
                            time.sleep(1)
                        else:
                            print("[DEPLOY] ⚠️ Timeout - Dashboard nicht erreichbar")
                            return {"content": [{"type": "text", "text": "✅ Deployment erfolgreich! Dashboard-Links konnten nicht aktiviert werden."}]}
                    
                    # 3. Aktiviere Dashboard-Links
                    print("[DEPLOY] 🎉 Aktiviere Dashboard-Links...")
                    for app_id in app_ids:
                        try:
                            # URL aktivieren
                            httpx.put(
                                f"https://my.living-apps.de/rest/apps/{app_id}/params/la_page_header_additional_url",
                                headers=headers,
                                json={"description": "dashboard_url", "type": "string", "value": dashboard_url},
                                timeout=10
                            )
                            # Title aktualisieren
                            httpx.put(
                                f"https://my.living-apps.de/rest/apps/{app_id}/params/la_page_header_additional_title",
                                headers=headers,
                                json={"description": "dashboard_title", "type": "string", "value": "Dashboard"},
                                timeout=10
                            )
                            print(f"[DEPLOY]   ✓ App {app_id} aktiviert")
                        except Exception as e:
                            print(f"[DEPLOY]   ✗ App {app_id}: {e}")
                    
                    print(f"[DEPLOY] ✅ Dashboard-Links erfolgreich hinzugefügt! ({time.time() - t_links_start:.1f}s)")
                    
                except Exception as e:
                    print(f"[DEPLOY] ⚠️ Fehler beim Hinzufügen der Dashboard-Links: {e}")

            t_deploy_total = time.time() - t_deploy_start
            print(f"[DEPLOY] ⏱️ Deploy gesamt: {t_deploy_total:.1f}s")
            return {
                "content": [{"type": "text", "text": f"✅ Deployment erfolgreich! ({t_deploy_total:.1f}s)"}]
            }

        except Exception as e:
            return {"content": [{"type": "text", "text": f"Deployment Failed: {str(e)}"}], "is_error": True}

    # ============================================================
    # NEW TOOL: create_apps
    # Creates LivingApps apps from JSON specification
    # Supports adding to existing apps (merges with app_metadata.json)
    # ============================================================
    @tool("create_apps",
        "Create LivingApps apps from a JSON specification. Call this BEFORE building the UI to get real types and API service. "
        "Saves metadata to app_metadata.json (used automatically by generate_typescript). "
        "Apps are created in dependency order (apps without applookup first). "
        "If apps already exist (app_metadata.json), new apps are ADDED to existing ones.",
        {
            "type": "object",
            "properties": {
                "apps": {
                    "type": "array",
                    "description": "Array of app definitions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Display name for the app"},
                            "identifier": {"type": "string", "description": "snake_case identifier (e.g. 'employees')"},
                            "controls": {"type": "object", "description": "Field definitions with fulltype, label, etc."}
                        },
                        "required": ["name", "identifier", "controls"]
                    }
                }
            },
            "required": ["apps"]
        }
    )
    async def create_apps(args):
        """Create LivingApps apps and return metadata for TypeScript generation."""
        import httpx
        
        apps = args.get("apps", [])
        api_key = os.environ.get("LIVINGAPPS_API_KEY")
        api_url = "https://my.living-apps.de/rest"
        
        if not apps:
            return {"content": [{"type": "text", "text": "Error: No apps specified"}], "is_error": True}
        
        if not api_key:
            return {"content": [{"type": "text", "text": "Error: LIVINGAPPS_API_KEY not set"}], "is_error": True}
        
        # Load existing metadata if present (to support adding apps later)
        existing_apps = {}
        existing_identifier_to_id = {}
        metadata_path = Path("app_metadata.json")
        
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    existing_metadata = json.load(f)
                    existing_apps = existing_metadata.get("apps", {})
                    # Build reverse lookup: identifier -> app_id
                    for identifier, app_data in existing_apps.items():
                        existing_identifier_to_id[identifier] = app_data["app_id"]
                    print(f"[LIVINGAPPS] 📂 Found {len(existing_apps)} existing apps, will add new ones")
            except Exception as e:
                print(f"[LIVINGAPPS] ⚠️ Could not read existing metadata: {e}")
        
        # Filter out apps that already exist
        new_apps = [app for app in apps if app["identifier"] not in existing_apps]
        
        if not new_apps:
            print("[LIVINGAPPS] ℹ️ All apps already exist, nothing to create")
            # Return existing metadata
            metadata = {
                "appgroup_id": None,
                "appgroup_name": "Auto-Generated",
                "apps": existing_apps,
                "metadata": {"apps_list": [app["name"] for app in existing_apps.values()]}
            }
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "success": True,
                        "message": "All apps already exist, no new apps created",
                        "existing_apps": list(existing_apps.keys()),
                        "metadata": metadata
                    }, indent=2)
                }]
            }
        
        import time
        t_create_start = time.time()
        print(f"[LIVINGAPPS] 🏗️ Creating {len(new_apps)} new apps...")
        
        # Sort by dependencies (apps without applookup first)
        sorted_apps = sort_apps_by_dependencies(new_apps)
        
        # Start with existing apps data
        created = dict(existing_apps)
        identifier_to_id = dict(existing_identifier_to_id)
        newly_created = []
        
        async with httpx.AsyncClient() as client:
            for app_def in sorted_apps:
                identifier = app_def["identifier"]
                
                # Build controls for API
                controls = {}
                for ctrl_name, ctrl in app_def.get("controls", {}).items():
                    ctrl_data = {
                        "fulltype": ctrl["fulltype"],
                        "label": ctrl["label"],
                        "required": ctrl.get("required", False),
                        "in_list": ctrl.get("in_list", False),
                        "in_text": ctrl.get("in_text", False),
                    }
                    
                    # Convert lookups array to dict format
                    # plan.md uses: [{"key": "x", "value": "Y"}]
                    # LivingApps API expects: {"x": "Y"}
                    if "lookups" in ctrl:
                        lookups = ctrl["lookups"]
                        if isinstance(lookups, list):
                            ctrl_data["lookups"] = {item["key"]: item["value"] for item in lookups}
                        else:
                            ctrl_data["lookups"] = lookups
                    
                    # Resolve applookup references to real app URLs
                    # Check both existing and newly created apps
                    if "applookup" in ctrl.get("fulltype", ""):
                        ref = ctrl.get("lookup_app_ref")
                        if ref and ref in identifier_to_id:
                            ctrl_data["lookup_app"] = f"{api_url}/apps/{identifier_to_id[ref]}"
                    
                    controls[ctrl_name] = ctrl_data
                
                # Create app via LivingApps REST API
                try:
                    print(f"[LIVINGAPPS] Creating: {app_def['name']}...")
                    response = await client.post(
                        f"{api_url}/apps",
                        json={"name": app_def["name"], "controls": controls},
                        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                        timeout=60
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    app_id = result["id"]
                    identifier_to_id[identifier] = app_id
                    created[identifier] = {
                        "app_id": app_id,
                        "name": app_def["name"],
                        "controls": result.get("controls", {})
                    }
                    newly_created.append(identifier)
                    print(f"[LIVINGAPPS] ✅ Created: {app_def['name']} ({app_id})")
                    
                except httpx.HTTPStatusError as e:
                    error_msg = f"Error creating '{app_def['name']}': {e.response.text}"
                    print(f"[LIVINGAPPS] ❌ {error_msg}")
                    return {
                        "content": [{"type": "text", "text": error_msg}],
                        "is_error": True
                    }
                except Exception as e:
                    error_msg = f"Error creating '{app_def['name']}': {str(e)}"
                    print(f"[LIVINGAPPS] ❌ {error_msg}")
                    return {
                        "content": [{"type": "text", "text": error_msg}],
                        "is_error": True
                    }
        
        # Build combined metadata (existing + new apps)
        metadata = {
            "appgroup_id": None,
            "appgroup_name": "Auto-Generated",
            "apps": created,
            "metadata": {"apps_list": [app["name"] for app in created.values()]}
        }
        
        # Save metadata to file for future reference
        try:
            with open("app_metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)
            print("[LIVINGAPPS] 💾 Saved app_metadata.json")
        except Exception as e:
            print(f"[LIVINGAPPS] ⚠️ Could not save metadata: {e}")
        
        t_create_total = time.time() - t_create_start
        print(f"[LIVINGAPPS] ✅ Created {len(newly_created)} new apps! Total apps: {len(created)} ({t_create_total:.1f}s)")
        
        response_payload = json.dumps({
            "success": True,
            "message": f"Created {len(newly_created)} new LivingApps apps ({t_create_total:.1f}s)",
            "apps_created": newly_created,
            "existing_apps": list(existing_apps.keys()),
            "total_apps": list(created.keys()),
            "metadata": metadata
        }, indent=2)
        
        print(f"\n{'='*80}")
        print(f"[CONTEXT] 🔧 TOOL RESPONSE: create_apps ({len(response_payload)} chars)")
        print(f"{'='*80}")
        print(response_payload)
        print(f"{'='*80}\n")
        
        return {
            "content": [{
                "type": "text",
                "text": response_payload
            }]
        }

    # ============================================================
    # NEW TOOL: generate_typescript
    # Generates TypeScript types and service from app metadata
    # ============================================================
    @tool("generate_typescript",
        "Generate TypeScript types, API service, and optionally CRUD page scaffolds. "
        "Call AFTER create_apps. Metadata is auto-read from app_metadata.json — do NOT pass it. "
        "Pass crud_scaffolds with entity identifiers to get ready-made CRUD pages with React Router. "
        "Only scaffold standard table-based CRUD entities. "
        "For custom UIs (kanban, calendar, tracker), omit them from crud_scaffolds.",
        {
            "type": "object",
            "properties": {
                "crud_scaffolds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity identifiers for which to generate CRUD page scaffolds. "
                                  "Use for standard table-based management entities (e.g. ['employees', 'categories']). "
                                  "Omit entities that need custom UI (kanban boards, calendars, trackers). "
                                  "Generates: Router, Layout with sidebar, CRUD pages with table+search+dialogs, "
                                  "Dashboard overview with KPI cards. Leave empty or omit for no scaffolding."
                }
            },
            "required": []
        }
    )
    async def generate_typescript(args):
        """Generate TypeScript files and optionally React CRUD scaffolds from app metadata."""
        crud_scaffolds = args.get("crud_scaffolds", [])
        
        # Auto-read metadata from file (saved by create_apps)
        metadata_path = Path("app_metadata.json")
        if not metadata_path.exists():
            return {"content": [{"type": "text", "text": "Error: app_metadata.json not found. Call create_apps first."}], "is_error": True}
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        print("[TYPESCRIPT] 📝 Generating TypeScript types and service...")
        
        try:
            # Import the generator (copied to sandbox by sandbox.py)
            from typescript_generator import TypeScriptGenerator
            
            generator = TypeScriptGenerator(metadata)
            types_code = generator.generate_types()
            service_code = generator.generate_service()
            
            # Ensure directories exist
            Path("src/types").mkdir(parents=True, exist_ok=True)
            Path("src/services").mkdir(parents=True, exist_ok=True)
            
            # Write files
            with open("src/types/app.ts", "w") as f:
                f.write(types_code)
            
            with open("src/services/livingAppsService.ts", "w") as f:
                f.write(service_code)
            
            generated_files = ["src/types/app.ts", "src/services/livingAppsService.ts"]
            
            print("[TYPESCRIPT] ✅ Generated src/types/app.ts")
            print("[TYPESCRIPT] ✅ Generated src/services/livingAppsService.ts")
            
            # Generate React CRUD scaffolds if requested
            if crud_scaffolds:
                print(f"[SCAFFOLD] 🏗️ Generating CRUD scaffolds for: {', '.join(crud_scaffolds)}")
                try:
                    from react_component_generator import ReactComponentGenerator
                    
                    react_gen = ReactComponentGenerator(metadata, crud_scaffolds)
                    react_files = react_gen.generate_all()
                    
                    for filepath, content in react_files.items():
                        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                        with open(filepath, "w") as f:
                            f.write(content)
                        generated_files.append(filepath)
                        print(f"[SCAFFOLD] ✅ Generated {filepath}")
                    
                    print(f"[SCAFFOLD] ✅ Generated {len(react_files)} React scaffold files")
                except ImportError:
                    print("[SCAFFOLD] ⚠️ react_component_generator.py not found — skipping scaffolds")
                except Exception as e:
                    print(f"[SCAFFOLD] ⚠️ Error generating scaffolds: {e} — continuing without scaffolds")
            
            # Build response: INSTRUCTIONS FIRST, then file contents
            # Agent reads the beginning most carefully — critical rules go at the top
            app_names = list(metadata.get("apps", {}).keys())
            
            response_text = f"Generated {len(generated_files)} files:\n"
            response_text += "\n".join(f"  - {f}" for f in generated_files)
            
            if crud_scaffolds:
                non_scaffolded = [k for k in app_names if k not in crud_scaffolds]
                response_text += f"\n\n{'='*60}"
                response_text += "\n📋 HINTS"
                response_text += f"\n{'='*60}"
                response_text += "\n"
                response_text += "\n1. CSS FORMAT: index.css uses oklch() colors and @theme inline — NOT hsl()!"
                response_text += "\n   EXTEND the existing :root block — do NOT rewrite from scratch."
                response_text += "\n   CSS import order MUST be: @import url(...) FIRST, then @import \"tailwindcss\", then @import \"tw-animate-css\"."
                response_text += "\n"
                response_text += "\n2. DashboardOverview.tsx — WRITE-ONCE RULE:"
                response_text += "\n   - Plan the ENTIRE component before writing (all imports, layout, charts)"
                response_text += "\n   - Keep ALL imports even if unused (bundler tree-shakes them)"
                response_text += "\n   - After writing DashboardOverview.tsx, move IMMEDIATELY to npm run build"
                response_text += "\n   - Do NOT read, review, verify, or rewrite DashboardOverview.tsx after writing it"
                response_text += "\n   - Do NOT convert var(--color-*) to hardcoded oklch values — CSS vars work fine in Recharts"
                response_text += "\n   - Accept the first version as FINAL. No cosmetic fixes, no class reorganization"
                response_text += "\n"
                response_text += "\nSTEPS (in order):"
                response_text += "\n  1. Edit index.css — EXTEND :root with your design tokens (oklch only!)"
                response_text += "\n  2. Edit APP_TITLE and APP_SUBTITLE in Layout.tsx"
                response_text += "\n  3. Write DashboardOverview.tsx (hero, KPIs, charts)"
                if non_scaffolded:
                    response_text += f"\n  4. Build custom pages for: {', '.join(non_scaffolded)}"
                response_text += f"\n  {'5' if non_scaffolded else '4'}. npm run build → fix errors → deploy_to_github"
                response_text += f"\n{'='*60}\n"
            
            # ═══════════════════════════════════════════════════════
            # FILE CONTENTS — key files included for reference
            # ═══════════════════════════════════════════════════════
            key_files = ["src/types/app.ts", "src/services/livingAppsService.ts"]
            if crud_scaffolds:
                key_files += ["src/App.tsx"]
                # NOTE: DashboardOverview.tsx intentionally NOT included — showing the scaffold
                # triggers the agent to read+rewrite it after writing its own version
                layout_path = Path("src/components/Layout.tsx")
                if layout_path.exists():
                    response_text += f"\n\n{'='*60}\n📄 src/components/Layout.tsx\n{'='*60}\n{layout_path.read_text()}"
            
            css_path = Path("src/index.css")
            if css_path.exists():
                response_text += f"\n\n{'='*60}\n📄 src/index.css\n{'='*60}\n{css_path.read_text()}"
            
            for fpath in key_files:
                fp = Path(fpath)
                if fp.exists():
                    response_text += f"\n\n{'='*60}\n📄 {fpath}\n{'='*60}\n{fp.read_text()}"
            
            if not crud_scaffolds:
                response_text += f"\n\nGenerated types for: {', '.join(app_names)}"
                response_text += "\n\n⚡ Key files are included above. Start coding immediately."
            
            print(f"\n{'='*80}")
            print(f"[CONTEXT] 🔧 TOOL RESPONSE: generate_typescript ({len(response_text)} chars)")
            print(f"{'='*80}")
            print(response_text)
            print(f"{'='*80}\n")
            
            return {"content": [{"type": "text", "text": response_text}]}
            
        except ImportError:
            return {
                "content": [{"type": "text", "text": "Error: typescript_generator.py not found in sandbox. Make sure it was copied."}],
                "is_error": True
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Error generating TypeScript: {str(e)}"}],
                "is_error": True
            }

    # ============================================================
    # CREATE MCP SERVER WITH ALL TOOLS
    # ============================================================
    dashboard_tools_server = create_sdk_mcp_server(
        name="dashboard_tools",
        version="1.0.0",
        tools=[deploy_to_github, create_apps, generate_typescript]
    )

    # 3. Optionen konfigurieren
    # setting_sources=["project"] is REQUIRED to load CLAUDE.md and .claude/skills/ from cwd
    options = ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code"
        },
        setting_sources=["project"],  # Required: loads CLAUDE.md and .claude/skills/
        mcp_servers={"dashboard_tools": dashboard_tools_server},
        permission_mode="acceptEdits",
        allowed_tools=[
            "Bash", "Write", "Read", "Edit", "Glob", "Grep", "Task", "TodoWrite",
            "mcp__dashboard_tools__deploy_to_github",
            "mcp__dashboard_tools__create_apps",
            "mcp__dashboard_tools__generate_typescript"
        ],
        cwd="/home/user/app",
        model="claude-sonnet-4-6"#"claude-opus-4-5-20251101"#, #"claude-sonnet-4-5-20250929"
    )

    # Session-Resume Unterstützung
    resume_session_id = os.getenv('RESUME_SESSION_ID')
    if resume_session_id:
        options.resume = resume_session_id
        print(f"[LILO] Resuming session: {resume_session_id}")

    # User Prompt - prefer file over env var (handles special chars better)
    user_prompt = None
    
    # First try reading from file (more reliable for special chars like umlauts)
    prompt_file = "/home/user/app/.user_prompt"
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r') as f:
                user_prompt = f.read().strip()
            if user_prompt:
                print(f"[LILO] Prompt aus Datei gelesen: {len(user_prompt)} Zeichen")
        except Exception as e:
            print(f"[LILO] Fehler beim Lesen der Prompt-Datei: {e}")
    
    # Fallback to env var (for backwards compatibility)
    if not user_prompt:
        user_prompt = os.getenv('USER_PROMPT')
        if user_prompt:
            print(f"[LILO] Prompt aus ENV gelesen")
    
    # Mode detection: UI_FIRST_MODE takes priority over generic USER_PROMPT handling
    ui_first_mode = os.getenv('UI_FIRST_MODE') == 'true'
    
    if ui_first_mode and user_prompt:
        # UI-First Mode: Neues Dashboard von Grund auf bauen
        # SANDBOX_PROMPT.md (= CLAUDE.md) enthält den kompletten Workflow
        query = f"""Baue ein neues Dashboard.

{user_prompt}"""
        print(f"[LILO] UI-First-Mode: Neues Dashboard bauen für: {user_prompt}")
    elif user_prompt:
        # Continue/Resume-Mode: Custom prompt vom User (existierendes Dashboard ändern)
        query = f"""🚨 AUFGABE: Du MUSST das existierende Dashboard ändern und deployen!

User-Anfrage: "{user_prompt}"

PFLICHT-SCHRITTE (alle müssen ausgeführt werden):

1. LESEN: Lies src/pages/Dashboard.tsx um die aktuelle Struktur zu verstehen
2. ÄNDERN: Implementiere die User-Anfrage mit dem Edit-Tool
3. TESTEN: Führe 'npm run build' aus um sicherzustellen dass es kompiliert
4. DEPLOYEN: Rufe deploy_to_github auf um die Änderungen zu pushen

⚠️ KRITISCH:
- Du MUSST Änderungen am Code machen (Edit-Tool verwenden!)
- Du MUSST am Ende deploy_to_github aufrufen!
- Beende NICHT ohne zu deployen!
- Analysieren alleine reicht NICHT - du musst HANDELN!

Das Dashboard existiert bereits. Mache NUR die angeforderten Änderungen, nicht mehr.
Starte JETZT mit Schritt 1!"""
        print(f"[LILO] Continue-Mode mit User-Prompt: {user_prompt}")
    else:
        # Normal-Mode: Neues Dashboard bauen
        # Check if we need to create apps (no app_metadata.json means fresh start)
        has_existing_metadata = Path("app_metadata.json").exists()
        has_existing_types = Path("src/types/app.ts").exists()
        
        if has_existing_metadata and has_existing_types:
            # Mode A: Existing apps - just build UI using them
            query = (
                "Use frontend-design Skill to analyze app structure and generate design_brief.md. "
                "Build the Dashboard.tsx following design_brief.md exactly. "
                "Use existing types and services from src/types/ and src/services/. "
                "Deploy when done using mcp__dashboard_tools__deploy_to_github."
            )
            print(f"[LILO] Build-Mode: Dashboard mit existierenden Apps erstellen")
        else:
            # Mode B: No apps yet - SANDBOX_PROMPT.md (CLAUDE.md) contains all instructions
            query = os.getenv('USER_PROMPT', 'Build a beautiful dashboard')
            print(f"[LILO] Build-Mode: Neues Dashboard (nur CLAUDE.md)")

    import time
    t_agent_total_start = time.time()
    print(f"[LILO] Initialisiere Client")

    # ═══════════════════════════════════════════════════════
    # CONTEXT WINDOW DEBUG: Print everything the agent sees
    # ═══════════════════════════════════════════════════════
    print(f"\n{'='*80}")
    print(f"[CONTEXT] 📋 SYSTEM PROMPT CONFIG:")
    print(f"  preset: claude_code")
    print(f"  setting_sources: ['project'] → loads CLAUDE.md + .claude/skills/ from cwd")
    print(f"  allowed_tools: {options.allowed_tools}")
    print(f"  model: {options.model}")
    print(f"{'='*80}")
    
    # Print CLAUDE.md content (= SANDBOX_PROMPT.md, the main system instructions)
    claude_md_path = Path("/home/user/app/CLAUDE.md")
    if claude_md_path.exists():
        claude_md = claude_md_path.read_text()
        print(f"\n{'='*80}")
        print(f"[CONTEXT] 📄 CLAUDE.md ({len(claude_md)} chars, {len(claude_md.splitlines())} lines):")
        print(f"{'='*80}")
        print(claude_md)
        print(f"{'='*80}")
    else:
        print(f"[CONTEXT] ⚠️ CLAUDE.md not found at {claude_md_path}")
    
    # Print skills if they exist
    skills_dir = Path("/home/user/app/.claude/skills")
    if skills_dir.exists():
        for skill_file in skills_dir.rglob("*.md"):
            skill_content = skill_file.read_text()
            print(f"\n[CONTEXT] 📄 SKILL: {skill_file} ({len(skill_content)} chars)")
            print(skill_content)
    else:
        print(f"[CONTEXT] ℹ️ No skills directory found")
    
    # Print the query (user message)
    print(f"\n{'='*80}")
    print(f"[CONTEXT] 💬 QUERY (user message to agent):")
    print(f"{'='*80}")
    print(query)
    print(f"{'='*80}\n")

    # 4. Der Client Lifecycle
    async with ClaudeSDKClient(options=options) as client:

        # Anfrage senden
        await client.query(query)

        # 5. Antwort-Schleife
        # receive_response() liefert alles bis zum Ende des Auftrags
        t_last_step = t_agent_total_start  # Track time of last output for delta calculation
        
        async for message in client.receive_response():
            now = time.time()
            elapsed = round(now - t_agent_total_start, 1)  # Total time since agent start
            dt = round(now - t_last_step, 1)               # Time since last step (step duration)
            t_last_step = now
            
            # A. Wenn er denkt oder spricht
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        #als JSON-Zeile ausgeben
                        print(json.dumps({"type": "think", "content": block.text, "t": elapsed, "dt": dt}), flush=True)
                    
                    elif isinstance(block, ToolUseBlock):
                        print(json.dumps({"type": "tool", "tool": block.name, "input": str(block.input), "t": elapsed, "dt": dt}), flush=True)

            # B. Wenn er fertig ist (oder Fehler)
            elif isinstance(message, ResultMessage):
                status = "success" if not message.is_error else "error"
                print(f"[LILO] Session ID: {message.session_id}")
                
                # Save session_id to file for future resume (AFTER ResultMessage)
                if message.session_id:
                    try:
                        with open("/home/user/app/.claude_session_id", "w") as f:
                            f.write(message.session_id)
                        print(f"[LILO] ✅ Session ID in Datei gespeichert")
                    except Exception as e:
                        print(f"[LILO] ⚠️ Fehler beim Speichern der Session ID: {e}")
                
                t_agent_total = time.time() - t_agent_total_start
                print(json.dumps({
                    "type": "result", 
                    "status": status, 
                    "cost": message.total_cost_usd,
                    "session_id": message.session_id,
                    "duration_s": round(t_agent_total, 1)
                }), flush=True)

if __name__ == "__main__":
    asyncio.run(main())