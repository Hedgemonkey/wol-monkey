"""Unit tests for domain entities — framework-free, no DB/network."""

from datetime import UTC, datetime

from app.domain.machine import Machine, WakeStrategy
from app.domain.probe import ProbeResult, ProbeState
from app.domain.wake_attempt import AttemptStatus


class TestMachine:
    def test_probe_host_uses_hostname_when_set(self) -> None:
        m = Machine(
            id="1",
            name="box",
            ip_address="192.168.1.10",
            mac_address="aa:bb:cc:dd:ee:ff",
            hostname="mybox.local",
        )
        assert m.probe_host() == "mybox.local"

    def test_probe_host_falls_back_to_ip(self) -> None:
        m = Machine(
            id="1",
            name="box",
            ip_address="192.168.1.10",
            mac_address="aa:bb:cc:dd:ee:ff",
        )
        assert m.probe_host() == "192.168.1.10"

    def test_wake_target_returns_mac(self) -> None:
        mac = "aa:bb:cc:dd:ee:ff"
        m = Machine(id="1", name="box", ip_address="10.0.0.1", mac_address=mac)
        assert m.wake_target() == mac

    def test_default_strategy_is_etherwake(self) -> None:
        m = Machine(id="1", name="box", ip_address="10.0.0.1", mac_address="aa:bb:cc:dd:ee:ff")
        assert m.wake_strategy == WakeStrategy.ETHERWAKE

    def test_enabled_defaults_true(self) -> None:
        m = Machine(id="1", name="box", ip_address="10.0.0.1", mac_address="aa:bb:cc:dd:ee:ff")
        assert m.enabled is True


class TestAttemptStatusTransitions:
    def test_pending_can_go_to_sent(self) -> None:
        assert AttemptStatus.PENDING.can_transition_to(AttemptStatus.SENT)

    def test_pending_can_go_to_failed(self) -> None:
        assert AttemptStatus.PENDING.can_transition_to(AttemptStatus.FAILED)

    def test_pending_cannot_go_to_online(self) -> None:
        assert not AttemptStatus.PENDING.can_transition_to(AttemptStatus.ONLINE)

    def test_sent_can_go_to_waking(self) -> None:
        assert AttemptStatus.SENT.can_transition_to(AttemptStatus.WAKING)

    def test_sent_can_go_to_online(self) -> None:
        assert AttemptStatus.SENT.can_transition_to(AttemptStatus.ONLINE)

    def test_sent_can_go_to_timeout(self) -> None:
        assert AttemptStatus.SENT.can_transition_to(AttemptStatus.TIMEOUT)

    def test_waking_can_go_to_online(self) -> None:
        assert AttemptStatus.WAKING.can_transition_to(AttemptStatus.ONLINE)

    def test_online_is_terminal(self) -> None:
        assert AttemptStatus.ONLINE.is_terminal

    def test_failed_is_terminal(self) -> None:
        assert AttemptStatus.FAILED.is_terminal

    def test_timeout_is_terminal(self) -> None:
        assert AttemptStatus.TIMEOUT.is_terminal

    def test_pending_is_not_terminal(self) -> None:
        assert not AttemptStatus.PENDING.is_terminal

    def test_terminal_has_no_transitions(self) -> None:
        for terminal in (AttemptStatus.ONLINE, AttemptStatus.FAILED, AttemptStatus.TIMEOUT):
            for target in AttemptStatus:
                assert not terminal.can_transition_to(target)


class TestProbeResult:
    def _result(self, ping: bool, tcp: bool) -> ProbeResult:
        return ProbeResult(
            machine_id="m1",
            ping_ok=ping,
            tcp_ssh_ok=tcp,
            observed_at=datetime.now(UTC),
        )

    def test_both_ok_is_online(self) -> None:
        assert self._result(True, True).derived_state == ProbeState.ONLINE

    def test_ping_only_is_online(self) -> None:
        assert self._result(True, False).derived_state == ProbeState.ONLINE

    def test_tcp_only_is_online(self) -> None:
        assert self._result(False, True).derived_state == ProbeState.ONLINE

    def test_both_fail_is_offline(self) -> None:
        assert self._result(False, False).derived_state == ProbeState.OFFLINE
