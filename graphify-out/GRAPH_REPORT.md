# Graph Report - C:\MY-AI  (2026-04-29)

## Corpus Check
- 74 files · ~51,571 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 287 nodes · 439 edges · 59 communities detected
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 81 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
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

## God Nodes (most connected - your core abstractions)
1. `ChatMessage` - 17 edges
2. `get_or_create_connection()` - 17 edges
3. `Memory` - 15 edges
4. `Task` - 15 edges
5. `InboxMessage` - 14 edges
6. `build_browser_prompt_plan()` - 14 edges
7. `UserProfile` - 13 edges
8. `IntegrationConnection` - 13 edges
9. `execute_desktop_command()` - 10 edges
10. `ChatRequest` - 8 edges

## Surprising Connections (you probably didn't know these)
- `save_chat_message()` --calls--> `ChatMessage`  [INFERRED]
  aura\backend\main.py → aura\backend\database.py
- `chat_stream_endpoint()` --calls--> `ChatMessage`  [INFERRED]
  aura\backend\main.py → aura\backend\database.py
- `_upsert_memory()` --calls--> `Memory`  [INFERRED]
  aura\backend\ai_engine.py → aura\backend\database.py
- `analyze_intent_and_memory()` --calls--> `Task`  [INFERRED]
  aura\backend\ai_engine.py → aura\backend\database.py
- `analyze_intent_and_memory()` --calls--> `execute_desktop_command()`  [INFERRED]
  aura\backend\ai_engine.py → aura\backend\automation.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (54): build_browser_prompt_plan(), build_voice_settings(), chat_stream_endpoint(), cloned_voice_configured(), create_calendar_reminder(), delete_scheduled_browser_automation(), detect_desktop_app(), detect_known_site() (+46 more)

### Community 1 - "Community 1"
Cohesion: 0.36
Nodes (20): Background task to extract memory and intent (e.g. creating tasks)., Generator for streaming responses., Base, BaseModel, ChatMessage, InboxMessage, IntegrationConnection, Memory (+12 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (19): addEvent(), addMinutes(), addTask(), buildIsoDate(), editEvent(), editTask(), extractStoredTime(), formatEventWindow() (+11 more)

### Community 3 - "Community 3"
Cohesion: 0.22
Nodes (15): addMinutes(), applyPlannerCommand(), cleanPlannerTitle(), extractDateValue(), extractTimeWindow(), findMatchingEvent(), findMatchingTask(), formatTime12h() (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.22
Nodes (2): handleKeyDown(), handleSend()

### Community 5 - "Community 5"
Cohesion: 0.24
Nodes (4): getSessionTitle(), readSessionTitles(), writeSessionTitle(), submitRename()

### Community 6 - "Community 6"
Cohesion: 0.22
Nodes (2): AkanshaAssistant(), useVoice()

### Community 7 - "Community 7"
Cohesion: 0.46
Nodes (7): _convert_pdfs_in_folder_to_ppts(), _create_folder(), execute_desktop_command(), _launch_windows_app(), _open_external_url(), Executes desktop and browser automation commands with best-effort safety., _resolve_folder_path()

### Community 8 - "Community 8"
Cohesion: 0.39
Nodes (4): addMessage(), sendMessage(), sendToAPI(), speak()

### Community 9 - "Community 9"
Cohesion: 0.48
Nodes (6): analyze_intent_and_memory(), _capture_deterministic_memories(), generate_chat_stream(), _normalize_user_fact(), _upsert_memory(), chat_endpoint()

### Community 10 - "Community 10"
Cohesion: 0.38
Nodes (3): createSessionId(), handleNewChatWithDetail(), startNewChat()

### Community 11 - "Community 11"
Cohesion: 0.29
Nodes (0): 

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (0): 

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (0): 

### Community 14 - "Community 14"
Cohesion: 0.33
Nodes (0): 

### Community 15 - "Community 15"
Cohesion: 0.4
Nodes (0): 

### Community 16 - "Community 16"
Cohesion: 0.6
Nodes (3): createSessionId(), handleNavClick(), openChat()

### Community 17 - "Community 17"
Cohesion: 0.67
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 0.67
Nodes (0): 

### Community 19 - "Community 19"
Cohesion: 0.67
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 0.67
Nodes (0): 

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (0): 

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

## Knowledge Gaps
- **1 isolated node(s):** `Executes desktop and browser automation commands with best-effort safety.`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 21`** (2 nodes): `image-hosts.config.mjs`, `next.config.mjs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `layout.tsx`, `RootLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `not-found.tsx`, `NotFound()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `page.tsx`, `RootPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `page.tsx`, `BrowserAutomationPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `page.tsx`, `ChannelIntegrationsPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `page.tsx`, `ChatInterfacePage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `MessageBubble.tsx`, `handleCopy()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `ModelSelector.tsx`, `ModelSelector()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `user.service.tsx`, `UserService()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `page.tsx`, `ConversationHistoryPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `FolderSidebar.tsx`, `FolderSidebar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `page.tsx`, `PlannerServicePage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `page.tsx`, `SignUpLoginPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `error.tsx`, `VoiceAssistantError()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `page.tsx`, `VoiceAssistantPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `tick()`, `AssistantAvatarStage.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `Avatar.tsx`, `Avatar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `PlannerServiceView.tsx`, `PlannerServiceView()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `build_graph.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `tailwind.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `AgentPanel.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `PromptTemplateModal.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `ConversationHistoryScreen.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `page.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `AuthBrandPanel.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `AuthScreen.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `AppLayout.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Topbar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `BrowserAutomationCenter.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `ChannelIntegrationsView.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `AppIcon.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `AppImage.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `AppLogo.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `speech-recognition.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `execute_desktop_command()` connect `Community 7` to `Community 0`, `Community 9`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **Why does `ChatMessage` connect `Community 1` to `Community 0`, `Community 9`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **Why does `Task` connect `Community 1` to `Community 9`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `ChatMessage` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`ChatMessage` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Memory` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`Memory` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Task` (e.g. with `Generator for streaming responses.` and `Background task to extract memory and intent (e.g. creating tasks).`) actually correct?**
  _`Task` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `InboxMessage` (e.g. with `ChatRequest` and `ChatMessageSaveRequest`) actually correct?**
  _`InboxMessage` has 12 INFERRED edges - model-reasoned connections that need verification._