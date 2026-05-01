from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Optional

from utils.wifi_uav_packets import build_ack_slot, build_fragment_ack_bitmap


SLOT_EMPTY = 0
SLOT_RECEIVING = 1
SLOT_COMPLETE = 2
SLOT_DELIVERED = 3
SLOT_DROPPED = 4


@dataclass
class WifiUavFrameSlot:
    """State for one native WiFi-UAV in-flight frame slot."""

    seq: int = 0
    status: int = SLOT_EMPTY
    fragment_total: int = 0
    frame_body_len: int = 0
    quality: int = 0
    fragments: dict[int, bytes] = field(default_factory=dict)
    received_fragments: set[int] = field(default_factory=set)

    def reset(self, seq: int, fragment_total: int, frame_body_len: int, quality: int) -> None:
        self.seq = seq
        self.status = SLOT_RECEIVING
        self.fragment_total = fragment_total
        self.frame_body_len = frame_body_len
        self.quality = quality
        self.fragments.clear()
        self.received_fragments.clear()

    def ingest(
        self,
        fragment_id: int,
        fragment_total: int,
        payload: bytes,
        *,
        frame_body_len: int = 0,
        quality: int = 0,
    ) -> None:
        if self.status in (SLOT_COMPLETE, SLOT_DELIVERED):
            return

        if self.status in (SLOT_EMPTY, SLOT_DELIVERED, SLOT_DROPPED):
            self.fragment_total = fragment_total
            self.frame_body_len = frame_body_len
            self.quality = quality
            self.status = SLOT_RECEIVING

        self.fragments[fragment_id] = payload
        self.received_fragments.add(fragment_id)

        if self.is_complete():
            self.status = SLOT_COMPLETE

    def is_complete(self) -> bool:
        return (
            self.fragment_total > 0
            and len(self.received_fragments) == self.fragment_total
            and all(i in self.fragments for i in range(self.fragment_total))
        )

    def ordered_payload(self) -> bytes:
        return b"".join(self.fragments[i] for i in range(self.fragment_total))

    def mark_delivered(self) -> None:
        self.status = SLOT_DELIVERED

    def mark_dropped(self) -> None:
        self.status = SLOT_DROPPED

    def ack_status(self) -> int:
        if self.status == SLOT_RECEIVING:
            return 0
        if self.status in (SLOT_COMPLETE, SLOT_DELIVERED):
            return 1
        if self.status == SLOT_DROPPED:
            return 2
        return 3

    def ack_bitmap(self) -> bytes:
        if self.status != SLOT_RECEIVING or self.fragment_total <= 0:
            return b""
        return build_fragment_ack_bitmap(self.fragment_total, self.received_fragments)

    def ack_slot(self) -> bytes:
        return build_ack_slot(self.seq, self.ack_status(), self.ack_bitmap())


class WifiUavAckState:
    """
    Four-slot ACK/frame tracker shaped after native build_send_ack().

    This keeps Turbodrone's delivery behavior simple while giving ACK generation
    a native-style home that can be evolved independently of socket code.
    """

    SLOT_COUNT = 4

    def __init__(self) -> None:
        self.slots = [WifiUavFrameSlot() for _ in range(self.SLOT_COUNT)]
        self.max_recv_seq = 0
        self.last_finished = 0
        self.last_completed_seq: Optional[int] = None
        self._delivered_history: deque[int] = deque(maxlen=32)

    def reset(self) -> None:
        for slot in self.slots:
            slot.seq = 0
            slot.status = SLOT_EMPTY
            slot.fragment_total = 0
            slot.frame_body_len = 0
            slot.quality = 0
            slot.fragments.clear()
            slot.received_fragments.clear()
        self.max_recv_seq = 0
        self.last_finished = 0
        self.last_completed_seq = None
        self._delivered_history.clear()

    def ingest_fragment(
        self,
        seq: int,
        fragment_id: int,
        fragment_total: int,
        payload: bytes,
        *,
        frame_body_len: int = 0,
        quality: int = 0,
    ) -> Optional[WifiUavFrameSlot]:
        if seq in self._delivered_history:
            return None

        slot = self._slot_for_seq(seq)
        if slot.seq != seq:
            slot.reset(seq, fragment_total, frame_body_len, quality)

        if fragment_total <= 0 or fragment_id >= fragment_total:
            return None

        self.max_recv_seq = max(self.max_recv_seq, seq)
        self.last_finished = seq
        slot.ingest(fragment_id, fragment_total, payload, frame_body_len=frame_body_len, quality=quality)
        if slot.is_complete():
            self.last_completed_seq = seq
            return slot
        return None

    def mark_delivered(self, seq: int) -> None:
        slot = self._find_slot(seq)
        if slot is not None:
            slot.mark_delivered()
        if seq not in self._delivered_history:
            self._delivered_history.append(seq)

    def mark_dropped(self, seq: int) -> None:
        slot = self._find_slot(seq)
        if slot is not None:
            slot.mark_dropped()

    def build_ack_slots(self, request_seq: int) -> list[bytes]:
        slots = []
        for slot in self.slots:
            if slot.status == SLOT_EMPTY or slot.seq == 0:
                continue
            if self.max_recv_seq and self.max_recv_seq - slot.seq >= 5:
                continue
            slots.append(slot.ack_slot())

        if slots:
            return slots

        return [
            build_ack_slot(request_seq, 1, b"\xff\xff\xff\xff"),
            build_ack_slot(request_seq, 3),
        ]

    def _slot_for_seq(self, seq: int) -> WifiUavFrameSlot:
        return self.slots[(seq + 3) % self.SLOT_COUNT]

    def _find_slot(self, seq: int) -> Optional[WifiUavFrameSlot]:
        for slot in self.slots:
            if slot.seq == seq:
                return slot
        return None
