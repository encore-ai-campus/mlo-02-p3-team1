class_name Sfx
extends RefCounted
## 효과음 + 배경음(BGM). 어디서든 Sfx.play("pickup") / Sfx.start_bgm() 처럼 부른다.
## 소리 파일: res://audio/sfx/<이름>.wav, res://audio/bgm/bgm_kkodakji_loop.wav
##   (tools/gen_audio.py, tools/gen_steps.py 가 만든다. 같은 이름 파일로 바꿔 끼우면 된다)
## 재생기는 처음 부를 때 루트에 하나 만들어 계속 쓴다. 씬이 바뀌어도 BGM 이 끊기지 않는다.
## 볼륨: "BGM", "SFX" 오디오 버스를 만들어 쓰고, 설정은 user://audio_settings.cfg 에 저장한다.
## 모든 버튼(BaseButton)은 눌릴 때 자동으로 click 소리를 낸다.
##
## 소리 이름: pickup 집기, place 놓기·조작, correct 정답, wrong 실수, clear 레벨·스테이지 클리어,
##   talk 대화 넘김, click 버튼, enter 컴퓨터(미니게임) 들어가기, boing NPC 말 걸기,
##   step_a / step_b 발소리, jump 점프, land 착지

const SFX_DIR := "res://audio/sfx/"
const BGM_PATH := "res://audio/bgm/bgm_kkodakji_loop.wav"
const SETTINGS_PATH := "user://audio_settings.cfg"
const VOICES := 8                 # 동시에 겹쳐 낼 수 있는 효과음 수
const BGM_BASE_DB := -12.0        # 배경음 기본 크기 (슬라이더 100% 일 때)

static var bgm_volume := 0.8      # 0..1
static var sfx_volume := 0.9
static var bgm_muted := false
static var sfx_muted := false
static var _streams := {}
static var _host: Node = null
static var _bgm: AudioStreamPlayer = null
static var _next := 0
static var _initialized := false

static func _enabled() -> bool:
	return DisplayServer.get_name() != "headless" and Engine.get_main_loop() is SceneTree

## 버스·설정·재생기 준비 (처음 한 번)
static func _setup() -> bool:
	if not _enabled():
		return false
	if _host != null and is_instance_valid(_host):
		return _host.is_inside_tree()
	if not _initialized:
		_initialized = true
		_load_settings()
	for bus in ["BGM", "SFX"]:
		if AudioServer.get_bus_index(bus) == -1:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, bus)
			AudioServer.set_bus_send(i, "Master")
	_apply_volumes()
	var tree := Engine.get_main_loop() as SceneTree
	_host = Node.new()
	_host.name = "SfxPlayers"
	_host.process_mode = Node.PROCESS_MODE_ALWAYS
	for i in VOICES:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		_host.add_child(p)
	_bgm = AudioStreamPlayer.new()
	_bgm.bus = "BGM"
	_bgm.volume_db = BGM_BASE_DB
	_host.add_child(_bgm)
	tree.root.add_child.call_deferred(_host)
	# 모든 버튼에 클릭 소리
	if not tree.node_added.is_connected(_on_node_added):
		tree.node_added.connect(_on_node_added)
	return false

static func _on_node_added(n: Node) -> void:
	if n is BaseButton and not n.has_meta("sfx_click"):
		n.set_meta("sfx_click", true)
		(n as BaseButton).pressed.connect(func(): play("click"))

static func _stream(path: String) -> AudioStream:
	if _streams.has(path):
		return _streams[path]
	if not ResourceLoader.exists(path):
		return null
	var s: AudioStream = load(path)
	_streams[path] = s
	return s

static func play(sound: String, pitch := 1.0, gain_db := 0.0) -> void:
	if not _setup():
		if _enabled() and _host != null:
			(func(): play(sound, pitch, gain_db)).call_deferred()   # 재생기가 다음 프레임에 트리에 붙는다
		return
	var stream := _stream(SFX_DIR + sound + ".wav")
	if stream == null:
		return
	var p := _host.get_child(_next % VOICES) as AudioStreamPlayer
	_next += 1
	p.stream = stream
	p.volume_db = gain_db
	p.pitch_scale = pitch
	p.play()

## 배경음 시작 (이미 나오고 있으면 그대로 둔다)
static func start_bgm() -> void:
	if not _setup():
		if _enabled() and _host != null:
			(func(): start_bgm()).call_deferred()
		return
	if _bgm.playing:
		return
	var s := _stream(BGM_PATH)
	if s == null:
		return
	if s is AudioStreamWAV and (s as AudioStreamWAV).loop_mode == AudioStreamWAV.LOOP_DISABLED:
		var w := s as AudioStreamWAV   # 가져오기 설정이 빠져도 반복되게
		w.loop_mode = AudioStreamWAV.LOOP_FORWARD
		w.loop_begin = 0
		w.loop_end = int(w.get_length() * w.mix_rate)
	_bgm.stream = s
	_bgm.play()

# ---------- 볼륨 설정 ----------
static func set_bgm_volume(v: float) -> void:
	bgm_volume = clampf(v, 0.0, 1.0)
	_apply_volumes()
	save_settings()

static func set_sfx_volume(v: float) -> void:
	sfx_volume = clampf(v, 0.0, 1.0)
	_apply_volumes()
	save_settings()

static func set_bgm_muted(m: bool) -> void:
	bgm_muted = m
	_apply_volumes()
	save_settings()

static func set_sfx_muted(m: bool) -> void:
	sfx_muted = m
	_apply_volumes()
	save_settings()

static func _apply_volumes() -> void:
	for pair in [["BGM", bgm_volume, bgm_muted], ["SFX", sfx_volume, sfx_muted]]:
		var i := AudioServer.get_bus_index(pair[0])
		if i == -1:
			continue
		AudioServer.set_bus_volume_db(i, linear_to_db(maxf(float(pair[1]), 0.0001)))
		AudioServer.set_bus_mute(i, bool(pair[2]) or float(pair[1]) <= 0.001)

static func _load_settings() -> void:
	var c := ConfigFile.new()
	if c.load(SETTINGS_PATH) != OK:
		return
	bgm_volume = clampf(float(c.get_value("audio", "bgm_volume", bgm_volume)), 0.0, 1.0)
	sfx_volume = clampf(float(c.get_value("audio", "sfx_volume", sfx_volume)), 0.0, 1.0)
	bgm_muted = bool(c.get_value("audio", "bgm_muted", false))
	sfx_muted = bool(c.get_value("audio", "sfx_muted", false))

static func save_settings() -> void:
	if not _enabled():
		return
	var c := ConfigFile.new()
	c.set_value("audio", "bgm_volume", bgm_volume)
	c.set_value("audio", "sfx_volume", sfx_volume)
	c.set_value("audio", "bgm_muted", bgm_muted)
	c.set_value("audio", "sfx_muted", sfx_muted)
	c.save(SETTINGS_PATH)

## 설정 화면이 열릴 때 저장된 값을 읽어 오도록
static func load_settings_now() -> void:
	_load_settings()
