# Voice exposure

Expose and unexpose entities to Home Assistant's voice assistants from scripts and automations.

Home Assistant only lets you change exposure one entity at a time in the UI, or through an admin websocket command. This integration adds two actions that call the same code, so a rule such as "everything labeled `voice`" can keep exposure up to date for you.

## Install

1. In HACS, go to **⋮ → Custom repositories**, add this repository's URL, and choose the type **Integration**.
2. Install **Voice exposure**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Voice exposure**. There's nothing to configure.

Without HACS, copy `custom_components/voice_exposure` into your `/config/custom_components/`, restart, and do step 3.

## Actions

### `voice_exposure.set`

Exposes or unexposes the entities you list.

```yaml
action: voice_exposure.set
data:
  entity_id: [light.office_ceiling, light.office_desk_lamp]
  expose: true
  assistants: [conversation]   # default; also cloud.alexa, cloud.google_assistant
  dry_run: false               # default
```

### `voice_exposure.sync`

Makes the entities in the list exposed. With `unexpose_others: true`, it also unexposes **every other** entity, so the list becomes exactly what's exposed. `dry_run` is **on by default**. Both actions return what changed, or what would change on a dry run:

```yaml
action: voice_exposure.sync
data:
  entity_id: "{{ label_entities('voice') }}"
  unexpose_others: true
  dry_run: false
response_variable: result
# result.assistants.conversation -> {exposed: [...], unexposed: [...], unchanged: 12}
```

If the list is empty and `unexpose_others` is on, a real run is refused, because that would unexpose everything. A dry run is still allowed, so you can see what it would do. An empty list almost always means a template went wrong. Use `set` with `expose: false` if you really want to unexpose things.

`conversation` is Assist. Custom conversation agents such as Jev or an LLM agent read the same setting.

## Exposing by label

The examples in [`examples/`](examples) keep Assist exposure in line with labels. They expose exactly what has the `voice` label, whether on the entity itself, on its device, or on its area, and unexpose everything else.

1. Create the labels `voice` and `no_voice` (**Settings → Areas, labels & zones → Labels**).
2. Add `voice` to areas, devices or entities. **Settings → Entities** lets you select entities in bulk and filter by area, domain and integration.
3. Add `no_voice` to anything inside a labeled area that shouldn't be exposed. Good candidates are config switches like an "LED indicator" or "Child lock", and the plain switch behind a `switch_as_x` light.
4. Add [`examples/script.yaml`](examples/script.yaml) and run it with **Make changes** off. A notification lists what it would expose and unexpose, even when that's nothing. With **Make changes** on, you only get a notification when something changed.
5. Once that list looks right, run it with **Make changes** on. If you want exposure kept in sync from then on, add [`examples/automation.yaml`](examples/automation.yaml) as well.

The script only exposes the kinds of entities listed in its `domains`. On purpose, it never exposes locks, alarm panels, or garage, gate and door covers. Add those only if you mean to.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```
