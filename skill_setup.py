"""First-run configuration. Never writes to Codex or skill directories."""
import json
import os
from pathlib import Path
import shutil
import tempfile


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix=path.name, suffix='.tmp', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def defaults(home=None, codex_home=None):
    home = Path(home) if home is not None else Path.home()
    codex = Path(codex_home) if codex_home is not None else Path(os.environ.get('CODEX_HOME', home / '.codex'))
    config = codex / 'config.toml'
    cache = codex / 'plugins' / 'cache'
    cli = codex / 'plugins' / '.plugin-appserver' / 'codex.exe'
    candidate = str(cli) if cli.is_file() else shutil.which('codex.exe') or ''
    roots = [(codex / 'skills', '用户 .codex / 系统技能'),
             (home / '.agents' / 'skills', '用户 .agents 技能')]
    return {'codex_config': str(config), 'codex_config_required': config.is_file(),
            'skill_roots': [{'path': str(path), 'label': label, 'required': path.is_dir()} for path, label in roots],
            'plugin_cache': str(cache), 'plugin_cache_required': cache.is_dir(),
            'known_plugins': [], 'plugin_cli': candidate}


def category_reference():
    groups = {
        '写作与内容': ['copy-editing', 'brand-storytelling', 'khazix-writer', 'writing-shape', 'video-marketing'],
        '社交平台': ['douyin', 'douyin-video', 'xiaohongshu', 'xiaohongshu-note-analyzer'],
        '工具与资料': ['imagegen', 'openai-docs', 'skill-creator', 'skill-installer', 'find-skills', 'obsidian-vault'],
    }
    return {name: {'category': category} for category, names in groups.items() for name in names}


def ensure(base):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    data = base / '.data'
    data.mkdir(exist_ok=True)
    settings_path = base / '设置.json'
    if not settings_path.exists():
        write_json(settings_path, defaults())
    settings = json.loads(settings_path.read_text(encoding='utf-8-sig'))
    previous = json.dumps(settings, sort_keys=True)
    # Once a monitored location exists, disappearance must fail closed.
    for entry in settings['skill_roots']:
        if Path(entry['path']).is_dir():
            entry['required'] = True
    for field, flag in [('codex_config', 'codex_config_required'), ('plugin_cache', 'plugin_cache_required')]:
        if Path(settings[field]).exists():
            settings[flag] = True
    if json.dumps(settings, sort_keys=True) != previous:
        write_json(settings_path, settings)
    for name, value in [('reference.json', category_reference()), ('历史导入.json', [])]:
        if not (data / name).exists():
            write_json(data / name, value)
    return settings
