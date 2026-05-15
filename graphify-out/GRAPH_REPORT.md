# Graph Report - C:\MY-AI  (2026-05-11)

## Corpus Check
- 86 files · ~112,758 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 464 nodes · 858 edges · 62 communities detected
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 155 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_FastAPI Endpoints|FastAPI Endpoints]]
- [[_COMMUNITY_Database Models|Database Models]]
- [[_COMMUNITY_Time Utilities|Time Utilities]]
- [[_COMMUNITY_Planner Logic|Planner Logic]]
- [[_COMMUNITY_Frontend Interaction|Frontend Interaction]]
- [[_COMMUNITY_Session Management|Session Management]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Desktop Automation|Desktop Automation]]
- [[_COMMUNITY_Voice & API Comms|Voice & API Comms]]
- [[_COMMUNITY_AI & Memory Engine|AI & Memory Engine]]
- [[_COMMUNITY_Chat Initialization|Chat Initialization]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Frontend Navigation|Frontend Navigation]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]

## God Nodes (most connected - your core abstractions)
1. `build_browser_prompt_plan()` - 27 edges
2. `ChatMessage` - 23 edges
3. `Memory` - 21 edges
4. `Task` - 21 edges
5. `InboxMessage` - 21 edges
6. `UserProfile` - 20 edges
7. `IntegrationConnection` - 19 edges
8. `SpeakerProfile` - 19 edges
9. `get_or_create_connection()` - 19 edges
10. `execute_desktop_command()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `save_chat_message()` --calls--> `ChatMessage`  [INFERRED]
  aura\backend\main.py → aura\backend\database.py
- `chat_stream_endpoint()` --calls--> `ChatMessage`  [INFERRED]
  aura\backend\main.py → aura\backend\database.py
- `verify_otp()` --calls--> `UserProfile`  [INFERRED]
  aura\backend\main.py → aura\backend\database.py
- `analyze_intent_and_memory()` --calls--> `execute_desktop_command()`  [INFERRED]
  aura\backend\ai_engine.py → aura\backend\automation.py
- `run_browser_automation()` --calls--> `execute_desktop_command()`  [INFERRED]
  aura\backend\main.py → aura\backend\automation.py

## Communities

### Community 0 - "FastAPI Endpoints"
Cohesion: 0.04
Nodes (95): build_browser_prompt_plan(), build_voice_settings(), chat_stream_endpoint(), _clean_contact_name(), _clean_message_body(), clean_social_config(), cloned_voice_configured(), connect_social_platform() (+87 more)

### Community 1 - "Database Models"
Cohesion: 0.09
Nodes (45): _clear_active_field(), _click_element_center(), _click_window_ratio(), _convert_pdfs_in_folder_to_ppts(), _create_folder(), execute_desktop_command(), _extract_amount(), _find_whatsapp_composer_element() (+37 more)

### Community 2 - "Time Utilities"
Cohesion: 0.25
Nodes (33): analyze_intent_and_memory(), _capture_deterministic_memories(), generate_chat_stream(), _normalize_user_fact(), Background task to extract memory and intent (e.g. creating tasks)., Generator for streaming responses., _upsert_memory(), Base (+25 more)

### Community 3 - "Planner Logic"
Cohesion: 0.17
Nodes (27): addMinutes(), applyPlannerCommand(), applyPlannerReminderFollowUp(), cleanPlannerTitle(), extractDateValue(), extractReminderTime(), extractTimeWindow(), findLatestEvent() (+19 more)

### Community 4 - "Frontend Interaction"
Cohesion: 0.13
Nodes (18): addEvent(), addMinutes(), addTask(), buildIsoDate(), editEvent(), editTask(), extractStoredTime(), formatEventWindow() (+10 more)

### Community 5 - "Session Management"
Cohesion: 0.11
Nodes (11): deleteSessionTitle(), getSessionTitle(), readSessionTitles(), writeSessionTitle(), handleDeleteConversation(), deleteConversation(), submitRename(), createSessionId() (+3 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (10): AkanshaAssistant(), buildVisemeTimeline(), clusterToVisemeParts(), consumeSpeechCluster(), indicClusterVisemes(), isHindiChar(), isIndicMark(), isTeluguChar() (+2 more)

### Community 7 - "Desktop Automation"
Cohesion: 0.17
Nodes (7): handleKeyDown(), handleSend(), expandSlashCommand(), findSlashCommand(), getSlashCommandSuggestions(), normalizeSlashCommandName(), parseSlashCommand()

### Community 8 - "Voice & API Comms"
Cohesion: 0.27
Nodes (11): arm_detached_windows_reminder(), _delete_reminder_marker(), normalize_reminder_text(), planner_reminder_scheduler_loop(), _powershell_single_quote(), _reminder_marker_path(), show_windows_notification(), startup_planner_scheduler() (+3 more)

### Community 9 - "AI & Memory Engine"
Cohesion: 0.25
Nodes (2): formatEventWindow(), formatTime12h()

### Community 10 - "Chat Initialization"
Cohesion: 0.33
Nodes (6): readConversationFolders(), readConversationMetadata(), readJson(), writeConversationFolders(), writeConversationMetadata(), writeJson()

### Community 11 - "Community 11"
Cohesion: 0.39
Nodes (4): addMessage(), sendMessage(), sendToAPI(), speak()

### Community 12 - "Community 12"
Cohesion: 0.25
Nodes (0): 

### Community 13 - "Community 13"
Cohesion: 0.38
Nodes (3): createSessionId(), handleNewChatWithDetail(), startNewChat()

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (0): 

### Community 15 - "Community 15"
Cohesion: 0.33
Nodes (0): 

### Community 16 - "Frontend Navigation"
Cohesion: 0.4
Nodes (0): 

### Community 17 - "Community 17"
Cohesion: 0.4
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 0.5
Nodes (0): 

### Community 19 - "Community 19"
Cohesion: 0.67
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 0.67
Nodes (0): 

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (2): getEmotionAwareAnchors(), tick()

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (2): isAutomationIntent(), normalizeAutomationPrompt()

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **1 isolated node(s):** `Executes desktop and browser automation commands with best-effort safety.`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 23`** (2 nodes): `image-hosts.config.mjs`, `next.config.mjs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `layout.tsx`, `RootLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `not-found.tsx`, `NotFound()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `page.tsx`, `RootPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `page.tsx`, `BrowserAutomationPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `page.tsx`, `ChannelIntegrationsPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `page.tsx`, `ChatInterfacePage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `MessageBubble.tsx`, `handleCopy()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `ModelSelector.tsx`, `ModelSelector()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `user.service.tsx`, `UserService()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `page.tsx`, `ConversationHistoryPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `ConversationHistoryScreen.tsx`, `buildLiveConversations()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `FolderSidebar.tsx`, `FolderSidebar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `page.tsx`, `PlannerServicePage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `page.tsx`, `SignUpLoginPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `error.tsx`, `VoiceAssistantError()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `page.tsx`, `VoiceAssistantPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `Avatar.tsx`, `Avatar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (2 nodes): `PlannerServiceView.tsx`, `PlannerServiceView()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (2 nodes): `App()`, `_app.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (2 nodes): `_document.tsx`, `Document()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `build_graph.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `tailwind.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `AgentPanel.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `PromptTemplateModal.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `page.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `AuthBrandPanel.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `AuthScreen.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `AppLayout.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Topbar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `BrowserAutomationCenter.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `ChannelIntegrationsView.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `AppIcon.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `AppImage.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `AppLogo.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `speech-recognition.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `connect_social_platform()` connect `FastAPI Endpoints` to `Frontend Interaction`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `update()` connect `Frontend Interaction` to `FastAPI Endpoints`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `execute_desktop_command()` connect `Database Models` to `FastAPI Endpoints`, `Time Utilities`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `ChatMessage` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`ChatMessage` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Memory` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`Memory` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Task` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`Task` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `InboxMessage` (e.g. with `ChatRequest` and `ChatMessageSaveRequest`) actually correct?**
  _`InboxMessage` has 19 INFERRED edges - model-reasoned connections that need verification._