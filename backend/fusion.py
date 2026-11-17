"""
Modality Fusion / Arbitration Module
-------------------------------------
Voice and gesture recognition currently run as two independent loops.
Without arbitration, if a user makes a gesture and speaks a command in
close succession (which happens often in dual-modality use -- e.g. saying
"click" while also pointing), BOTH actions would fire. This module adds
a confidence-weighted decision rule so only one action executes when the
two modalities disagree within a short time window.

How it works
------------
1. When a modality recognizes a mapped action, it calls `propose()`.
2. If the *other* modality already has an unresolved proposal from within
   the last `fusion_window` seconds, the two are compared immediately:
   the one with the higher (confidence * modality_weight) score wins,
   and only that action is executed.
3. If there is no competing proposal yet, `propose()` polls in short
   intervals (yielding control via the caller-supplied cooperative
   `sleep_fn`, e.g. `socketio.sleep`) until either a competing proposal
   arrives (-> resolve immediately) or the window elapses (-> execute
   alone, since nothing else was competing for that action slot).

Design choice: the calling code (app.py) only invokes fusion when BOTH
gesture and voice loops are simultaneously enabled. In single-modality
use -- the common case -- there is nothing to arbitrate, so actions
execute immediately with zero added latency. The fusion window only
costs latency in true dual-modality operation, which is exactly when
arbitration is needed.
"""

import threading
import time


class ModalityFusion:
    """Confidence-weighted arbitration between the 'gesture' and 'voice' modalities."""

    def __init__(self, fusion_window=1.0, gesture_weight=1.0, voice_weight=1.0,
                 poll_interval=0.1, logger=None):
        self.fusion_window = fusion_window
        self.weights = {'gesture': gesture_weight, 'voice': voice_weight}
        self.poll_interval = poll_interval
        self.logger = logger

        self._lock = threading.Lock()
        self._pending = {}  # modality -> {action, confidence, raw, timestamp, resolved}

    def update_settings(self, fusion_window=None, gesture_weight=None, voice_weight=None):
        with self._lock:
            if fusion_window is not None:
                self.fusion_window = fusion_window
            if gesture_weight is not None:
                self.weights['gesture'] = gesture_weight
            if voice_weight is not None:
                self.weights['voice'] = voice_weight

    @staticmethod
    def _other(modality):
        return 'voice' if modality == 'gesture' else 'gesture'

    def propose(self, modality, action, confidence, raw_label, sleep_fn):
        """
        Register a candidate action from `modality` and decide whether the
        caller should execute it.

        `sleep_fn` must be a cooperative sleep (e.g. socketio.sleep) so the
        other modality's background loop keeps running while this one waits.

        Returns:
            {
              'execute': bool,     # True -> caller should run `action`
              'winner': str|None,  # modality whose action should run
              'reason': str        # short machine-readable reason (for logs)
            }
        """
        now = time.time()
        other = self._other(modality)

        with self._lock:
            self._pending[modality] = {
                'action': action, 'confidence': confidence,
                'raw': raw_label, 'timestamp': now, 'resolved': False,
            }
            competing = self._pending.get(other)
            competing_is_fresh = (
                competing is not None and not competing['resolved']
                and (now - competing['timestamp']) <= self.fusion_window
            )

        if competing_is_fresh:
            return self._resolve(modality, other)

        # No competing proposal yet -- poll until the window elapses or
        # a competing proposal shows up, whichever happens first.
        #
        # IMPORTANT: we must also check whether the *other* thread has, in
        # the meantime, already resolved this proposal for us (it registers
        # after we do, sees us as "fresh", and calls _resolve on both
        # entries). Without this check, both sides could independently
        # decide "no competing event" and both execute. So every iteration
        # checks our own entry's 'resolved'/'decision' fields first.
        elapsed = 0.0
        step = max(0.01, min(self.poll_interval, self.fusion_window))
        while elapsed < self.fusion_window:
            sleep_fn(step)
            elapsed += step

            with self._lock:
                mine = self._pending.get(modality)
                if mine is not None and mine['resolved'] and 'decision' in mine:
                    return mine['decision']

                competing = self._pending.get(other)
                still_fresh = (
                    competing is not None and not competing['resolved']
                    and (time.time() - competing['timestamp']) <= self.fusion_window
                )
            if still_fresh:
                return self._resolve(modality, other)

        # Window elapsed with nothing competing -- but double-check one last
        # time that we weren't resolved by the other side in the final
        # instant between our last poll and now.
        with self._lock:
            entry = self._pending.get(modality)
            if entry is not None and entry['resolved'] and 'decision' in entry:
                return entry['decision']
            if entry:
                decision = {'execute': True, 'winner': modality, 'reason': 'no_competing_event'}
                entry['resolved'] = True
                entry['decision'] = decision
            else:
                decision = {'execute': True, 'winner': modality, 'reason': 'no_competing_event'}

        self._log(modality, action, confidence, decision)
        return decision

    def _resolve(self, modality, other):
        with self._lock:
            mine = self._pending.get(modality)
            theirs = self._pending.get(other)

            if mine is None:
                return {'execute': False, 'winner': other, 'reason': 'missing_self_entry'}

            if mine['resolved'] and 'decision' in mine:
                return mine['decision']

            if theirs is None or theirs['resolved']:
                decision = {'execute': True, 'winner': modality, 'reason': 'competitor_already_resolved'}
                mine['resolved'] = True
                mine['decision'] = decision
                self._log(modality, mine['action'], mine['confidence'], decision)
                return decision

            my_score = mine['confidence'] * self.weights.get(modality, 1.0)
            their_score = theirs['confidence'] * self.weights.get(other, 1.0)

            if my_score >= their_score:
                my_decision = {
                    'execute': True, 'winner': modality,
                    'reason': f'higher_score_{my_score:.3f}_vs_{their_score:.3f}',
                }
                their_decision = {
                    'execute': False, 'winner': modality,
                    'reason': f'lower_score_{their_score:.3f}_vs_{my_score:.3f}',
                }
            else:
                my_decision = {
                    'execute': False, 'winner': other,
                    'reason': f'lower_score_{my_score:.3f}_vs_{their_score:.3f}',
                }
                their_decision = {
                    'execute': True, 'winner': other,
                    'reason': f'higher_score_{their_score:.3f}_vs_{my_score:.3f}',
                }

            mine['resolved'] = True
            mine['decision'] = my_decision
            theirs['resolved'] = True
            theirs['decision'] = their_decision

            self._log(
                modality, mine['action'], mine['confidence'], my_decision,
                competing_modality=other, competing_confidence=theirs['confidence'],
                competing_action=theirs['action'],
            )
            return my_decision

    def _log(self, modality, action, confidence, decision,
              competing_modality=None, competing_confidence=None, competing_action=None):
        if not self.logger:
            return
        self.logger.log_event(
            event_type='fusion_decision',
            modality=modality,
            action=action,
            confidence=confidence,
            extra={
                'winner': decision['winner'],
                'executed': decision['execute'],
                'reason': decision['reason'],
                'competing_modality': competing_modality,
                'competing_confidence': competing_confidence,
                'competing_action': competing_action,
                'fusion_window': self.fusion_window,
            },
        )
