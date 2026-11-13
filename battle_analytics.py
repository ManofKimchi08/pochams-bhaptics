import time
from typing import List, Dict, Any, Optional, Tuple

class BattleAnalytics:
    """
    📊 포챔스 배틀 세션 실시간 통계 및 피격 분석기
    - 배틀 총 누적 피해량 / 회복량
    - 피격 등급별(경타/중타/강타/치명타/기절) 횟수 집계
    - 최고 피격 대미지 및 최저 생존 체력 기록
    - 타임스탬프 기반 상세 피격 타임라인
    - 디스코드/커뮤니티 공유용 텍스트 리포트 생성
    """

    def __init__(self):
        self.session_start_time: float = time.time()
        self.total_damage_pct: float = 0.0
        self.total_heal_pct: float = 0.0
        self.hit_counts: Dict[str, int] = {
            "light": 0,
            "medium": 0,
            "heavy": 0,
            "critical": 0,
            "faint": 0
        }
        self.max_single_hit: Tuple[float, str, str] = (0.0, "none", "--:--:--") # (damage, level, time_str)
        self.min_hp_survived: float = 100.0
        self.faint_count: int = 0
        self.events: List[Dict[str, Any]] = []
        self.switches_count: int = 0

    def reset_session(self) -> None:
        """새 배틀 세션 시작 (통계 초기화)"""
        self.session_start_time = time.time()
        self.total_damage_pct = 0.0
        self.total_heal_pct = 0.0
        self.hit_counts = {"light": 0, "medium": 0, "heavy": 0, "critical": 0, "faint": 0}
        self.max_single_hit = (0.0, "none", "--:--:--")
        self.min_hp_survived = 100.0
        self.faint_count = 0
        self.events.clear()
        self.switches_count = 0

    def record_damage(self, delta_hp: float, current_hp_pct: float, level_key: str, level_name: str) -> None:
        """피격 대미지 이벤트 기록"""
        t_str = time.strftime("%H:%M:%S")
        self.total_damage_pct += delta_hp
        
        if level_key == "faint":
            # 기절 타격 시에도 실제 깎인 체력 비율에 따라 경타/중타/강타/치명타 분포에 합산
            if delta_hp >= 80.0:
                dmg_tier = "critical"
            elif delta_hp >= 50.0:
                dmg_tier = "heavy"
            elif delta_hp >= 20.0:
                dmg_tier = "medium"
            else:
                dmg_tier = "light"
            self.hit_counts[dmg_tier] += 1
        elif level_key in self.hit_counts:
            self.hit_counts[level_key] += 1
            
        if delta_hp > self.max_single_hit[0]:
            self.max_single_hit = (delta_hp, level_name, t_str)
            
        if 0.0 < current_hp_pct < self.min_hp_survived:
            self.min_hp_survived = current_hp_pct

        if current_hp_pct <= 0.0 or level_key == "faint":
            self.faint_count += 1
            self.hit_counts["faint"] += 1

        self.events.append({
            "time": t_str,
            "type": "DAMAGE",
            "delta": delta_hp,
            "hp": current_hp_pct,
            "level": level_name,
            "desc": f"-{delta_hp:.1f}% ({level_name}) -> 잔여 HP: {current_hp_pct:.1f}%"
        })

    def record_heal(self, delta_hp: float, current_hp_pct: float) -> None:
        """체력 회복 이벤트 기록"""
        t_str = time.strftime("%H:%M:%S")
        self.total_heal_pct += delta_hp
        self.events.append({
            "time": t_str,
            "type": "HEAL",
            "delta": delta_hp,
            "hp": current_hp_pct,
            "level": "회복",
            "desc": f"+{delta_hp:.1f}% (체력 회복) -> 잔여 HP: {current_hp_pct:.1f}%"
        })

    def record_switch(self, old_max: int, new_max: int, new_hp_pct: float) -> None:
        """포켓몬 교체 기록"""
        t_str = time.strftime("%H:%M:%S")
        self.switches_count += 1
        self.events.append({
            "time": t_str,
            "type": "SWITCH",
            "delta": 0.0,
            "hp": new_hp_pct,
            "level": "교체",
            "desc": f"포켓몬 교체 (최대 HP: {old_max} -> {new_max}, 현재: {new_hp_pct:.1f}%)"
        })

    def get_summary_dict(self) -> Dict[str, Any]:
        """대시보드 UI 표시용 요약 딕셔너리"""
        now = time.time()
        elapsed_sec = int(now - self.session_start_time)
        mins, secs = divmod(elapsed_sec, 60)
        
        total_hits = (
            self.hit_counts["light"] +
            self.hit_counts["medium"] +
            self.hit_counts["heavy"] +
            self.hit_counts["critical"]
        )

        return {
            "elapsed_str": f"{mins:02d}:{secs:02d}",
            "total_damage": self.total_damage_pct,
            "total_heal": self.total_heal_pct,
            "total_hits": total_hits,
            "hit_counts": self.hit_counts,
            "max_hit_damage": self.max_single_hit[0],
            "max_hit_level": self.max_single_hit[1],
            "max_hit_time": self.max_single_hit[2],
            "min_hp_survived": self.min_hp_survived if self.min_hp_survived < 100.0 else 100.0,
            "faint_count": self.faint_count,
            "switches_count": self.switches_count,
            "events_count": len(self.events)
        }

    def generate_clipboard_report(self) -> str:
        """디스코드나 커뮤니티에 즉시 붙여넣을 수 있는 깔끔한 리포트 텍스트 생성"""
        s = self.get_summary_dict()
        t_now = time.strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [
            "🏆 [PokéChamps x bHaptics] 배틀 피격 분석 리포트",
            "━" * 32,
            f"📅 측정 일시 : {t_now}",
            f"⏱️ 진행 시간 : {s['elapsed_str']}",
            f"💥 총 누적 대미지 : {s['total_damage']:.1f}% (체력 약 {s['total_damage'] / 100.0:.1f}줄 손실)",
            f"🎯 총 피격 횟수 : {s['total_hits']}회",
            f"   - 🔹 경타 (1~20%)   : {s['hit_counts']['light']}회",
            f"   - 🔸 중타 (21~50%)  : {s['hit_counts']['medium']}회",
            f"   - 🔻 강타 (51~80%)  : {s['hit_counts']['heavy']}회",
            f"   - ⚡ 치명타 (81~100%) : {s['hit_counts']['critical']}회",
        ]
        
        if s['max_hit_damage'] > 0:
            lines.append(f"⚡ 최대 피격 피해 : -{s['max_hit_damage']:.1f}% [{s['max_hit_level']}] ({s['max_hit_time']})")
            
        if s['min_hp_survived'] < 100.0:
            lines.append(f"🛡️ 최저 생존 체력 : {s['min_hp_survived']:.1f}% 버팀")
            
        if s['faint_count'] > 0:
            lines.append(f"💀 기절 횟수 : {s['faint_count']}회")
            
        if s['switches_count'] > 0:
            lines.append(f"🔄 교체 횟수 : {s['switches_count']}회")
            
        lines.append("━" * 32)
        lines.append("🎮 PokéChamps x bHaptics Tactile Link")
        return "\n".join(lines)
