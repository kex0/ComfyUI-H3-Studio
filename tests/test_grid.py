import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "face_refine"))

from grid import (
    CHUNK_OVERLAP, align_h3_frames, canvas_rect_to_source, chunk_is_all_closeup,
    chunk_ranges,     closeup_paste_weight, denoise_px_range, face_ellipse_mask, face_rect_in_canvas,
    face_token_video_mask, fit_box_to_aspect, h3_frame_groups, h3_latent_t,
    h3_steps_covering, latent_mask_to_frames, pack_av_noise_mask, pack_refine_chunks,
    pack_refine_jobs, per_frame_strength, plan_hold_teleports, follow_face_boxes,
    reduce_mask_h3, refine_paste_weight, select_chunk_span, shot_breaks_from_boxes,
    shot_breaks_from_tracks, smooth_per_shot, closeup_paste_gate,
    sharpness_match_amount, segment_hold, job_hold, shot_spans, hard_cut_breaks,
    overlap_freeze_scale, committed_write_span, committed_file_spans, debug_file_slice,
    audio_mux_duration, sustained_visible, MIN_VISIBLE_SEC, wrap_refine_window,
    loop_span_len,
)


class TestSelectChunkSpan(unittest.TestCase):
    def test_auto_resume(self):
        self.assertEqual(select_chunk_span(10, 0, 0, completed_chunk=4), (4, 9))

    def test_explicit_range(self):
        self.assertEqual(select_chunk_span(10, 1, 5, completed_chunk=9), (0, 4))

    def test_continue_from_six(self):
        self.assertEqual(select_chunk_span(10, 6, 0), (5, 9))

    def test_already_done(self):
        first, last = select_chunk_span(10, 0, 0, completed_chunk=10)
        self.assertGreater(first, last)

    def test_end_clamped(self):
        self.assertEqual(select_chunk_span(3, 1, 99), (0, 2))


class TestChunkRanges(unittest.TestCase):
    def test_abutting_is_unchanged(self):
        chunks = chunk_ranges(500, 243, overlap=0)
        self.assertEqual(chunks[0], (0, 243, 243))
        self.assertEqual(chunks[1][0], 243)

    def test_overlap_strides_context_frames(self):
        m = align_h3_frames(240)
        chunks = chunk_ranges(500, m, overlap=CHUNK_OVERLAP)
        self.assertEqual(CHUNK_OVERLAP, 22)
        self.assertEqual(chunks[0][1] - chunks[0][0], m)
        self.assertEqual(chunks[1][0], chunks[0][1] - CHUNK_OVERLAP)
        self.assertEqual(chunks[1][1] - chunks[1][0], m)
        self.assertEqual(chunks[-1][1], 500)

    def test_union_covers_every_frame(self):
        n = 4000
        m = align_h3_frames(240)
        chunks = chunk_ranges(n, m, overlap=CHUNK_OVERLAP)
        covered = set()
        for start, end, _grid in chunks:
            covered.update(range(start, end))
        self.assertEqual(covered, set(range(n)))
        self.assertGreater(len(chunks), 1)

    def test_delayed_write_counts_equal_n(self):
        n, overlap = 500, CHUNK_OVERLAP
        chunks = chunk_ranges(n, align_h3_frames(240), overlap=overlap)
        written = 0
        pending = 0
        for i, (start, end, _grid) in enumerate(chunks):
            body = end - start
            is_last = i == len(chunks) - 1
            hold = 0 if is_last else min(overlap, body)
            written += body - hold
            pending = hold
        self.assertEqual(written + pending, n)

    def test_overlap_ignored_when_not_smaller_than_chunk(self):
        chunks = chunk_ranges(20, 5, overlap=17)
        self.assertEqual(chunks[0][0], 0)

    def test_single_short_clip(self):
        chunks = chunk_ranges(80, 243, overlap=17)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0][0], 0)
        self.assertEqual(chunks[0][1], 80)


class TestPackRefineChunks(unittest.TestCase):
    def test_all_need_matches_uniform_chunks(self):
        n, m = 500, 243
        packed = pack_refine_chunks(np.ones(n, dtype=bool), n, m, overlap=17)
        old = chunk_ranges(n, m, overlap=17)
        self.assertEqual([(a, b, g) for a, b, g, k in packed], old)
        self.assertTrue(all(k == "refine" for _, _, _, k in packed))

    def test_no_need_is_one_copy(self):
        segs = pack_refine_chunks(np.zeros(100, dtype=bool), 100, 243, overlap=17)
        self.assertEqual(segs, [(0, 100, 100, "copy")])

    def test_tail_of_six_plus_head_of_seven_merge(self):
        n = 486
        need = np.zeros(n, dtype=bool)
        need[170:316] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 170)
        self.assertEqual(refine[0][1], 316)
        self.assertLess(refine[0][2], 243)
        copies = [s for s in segs if s[3] == "copy"]
        self.assertEqual(copies[0], (0, 170, 170, "copy"))
        self.assertEqual(copies[-1][0], 316)

    def test_far_apart_needs_stay_split(self):
        n = 800
        need = np.zeros(n, dtype=bool)
        need[10:80] = True
        need[400:470] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 2)
        self.assertEqual(refine[0][1], 80)
        self.assertEqual(refine[1][0], 400)

    def test_same_shot_skip_hole_stays_in_h3(self):
        n = 400
        need = np.zeros(n, dtype=bool)
        need[100:163] = True
        need[200:275] = True
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(need, n, 243, overlap=22, breaks=breaks)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertGreaterEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[-1][1], n)
        self.assertFalse(any(s[3] == "copy" for s in segs))

    def test_trailing_closeup_stays_in_shot_hull(self):
        n = 200
        need = np.zeros(n, dtype=bool)
        need[20:80] = True
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(need, n, 243, overlap=22, breaks=breaks)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[0][1], n)
        self.assertFalse(any(s[3] == "copy" for s in segs))

    def test_two_shots_stay_split(self):
        n = 200
        need = np.zeros(n, dtype=bool)
        need[10:80] = True
        need[120:170] = True
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        breaks[100] = True
        segs = pack_refine_chunks(need, n, 243, overlap=22, breaks=breaks)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 2)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[0][1], 100)
        self.assertEqual(refine[1][0], 100)
        self.assertEqual(refine[1][1], n)

    def test_long_shot_splits_with_overlap_not_copy(self):
        n = 500
        need = np.ones(n, dtype=bool)
        need[200:240] = False
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(need, n, 243, overlap=22, breaks=breaks)
        self.assertFalse(any(s[3] == "copy" for s in segs))
        refine = [s for s in segs if s[3] == "refine"]
        self.assertGreater(len(refine), 1)
        self.assertEqual(refine[1][0], refine[0][1] - 22)

    def test_shot_spans(self):
        br = np.zeros(10, dtype=bool)
        br[0] = True
        br[4] = True
        self.assertEqual(shot_spans(br, 10), [(0, 4), (4, 10)])

    def test_zoom_is_not_a_hard_cut(self):
        boxes = [(800, 400, 200, 200)] * 5
        boxes[3] = (790, 400, 80, 80)
        boxes[4] = (790, 400, 80, 80)
        br = hard_cut_breaks(boxes, 1728, 960)
        self.assertFalse(bool(br[3]))

    def test_big_pan_is_a_hard_cut(self):
        boxes = [(100, 400, 200, 200), (900, 400, 200, 200)]
        br = hard_cut_breaks(boxes, 1728, 960)
        self.assertTrue(bool(br[1]))

    def test_zoom_skip_is_not_a_maskvid_teleport(self):
        n = 300
        need = np.zeros(n, dtype=bool)
        need[40:100] = True
        need[140:220] = True
        boxes = [(400, 300, 180, 180)] * n
        for i in range(100, 140):
            boxes[i] = (400, 300, 400, 400)
        breaks = hard_cut_breaks(boxes, 1728, 960)
        self.assertFalse(bool(breaks[100]))
        segs = pack_refine_chunks(need, n, 243, overlap=22, breaks=breaks)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertGreaterEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[-1][1], n)
        self.assertFalse(any(s[3] == "copy" for s in segs))

    def test_maskvid_breaks_win_over_box_pan(self):
        n = 200
        need = np.ones(n, dtype=bool)
        boxes = [(100, 400, 200, 200)] * 100 + [(900, 400, 200, 200)] * 100
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(
            need, n, 243, overlap=17, breaks=breaks, boxes=boxes, src_size=(1728, 960),
        )
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[0][1], n)

    def test_zoom_skip_hole_merges_with_boxes(self):
        n = 300
        need = np.zeros(n, dtype=bool)
        need[40:100] = True
        need[140:220] = True
        boxes = [(400, 300, 180, 180)] * n
        for i in range(100, 140):
            boxes[i] = (400, 300, 400, 400)
        segs = pack_refine_chunks(
            need, n, 243, overlap=22, boxes=boxes, src_size=(1728, 960),
        )
        refine = [s for s in segs if s[3] == "refine"]
        self.assertGreaterEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[-1][1], n)
        self.assertFalse(any(s[3] == "copy" for s in segs))

    def test_tiny_hull_is_copied(self):
        n = 80
        need = np.zeros(n, dtype=bool)
        need[10:15] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17)
        self.assertTrue(all(s[3] == "copy" for s in segs))

    def test_timeline_is_covered(self):
        n = 900
        need = np.zeros(n, dtype=bool)
        need[40:90] = True
        need[200:500] = True
        need[820:880] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17)
        cover = np.zeros(n, dtype=np.int32)
        for a, b, _g, _k in segs:
            cover[a:b] += 1
        self.assertTrue(np.all(cover >= 1))

    def test_hold_only_between_overlapping_refine(self):
        segs = [
            (0, 100, 100, "copy"),
            (100, 343, 243, "refine"),
            (326, 500, 174, "refine"),
            (500, 600, 100, "copy"),
        ]
        self.assertEqual(segment_hold(segs, 0, 22), 0)
        self.assertEqual(segment_hold(segs, 1, 17), 17)
        self.assertEqual(segment_hold(segs, 2, 22), 0)

    def test_copy_then_overlapping_h3_skips_committed_prefix(self):
        self.assertEqual(
            committed_write_span(1371, 1614, 1371, hold=0, is_last=True),
            (1371, 1614),
        )
        self.assertEqual(
            committed_write_span(1592, 1835, 1614, hold=22, is_last=False),
            (1614, 1813),
        )
        self.assertEqual(
            committed_write_span(1592, 1835, 1592, hold=22, is_last=False),
            (1592, 1813),
        )
        self.assertEqual(
            committed_write_span(1813, 1894, 1813, hold=0, is_last=True),
            (1813, 1894),
        )

    def test_long_shot_write_spans_hold_continue_overlap(self):
        segs = [
            (3306, 3549, 243, "refine"),
            (3527, 3770, 243, "refine"),
            (3748, 3848, 107, "refine"),
            (3848, 4102, 254, "copy"),
        ]
        spans = committed_file_spans(segs, 22)
        self.assertEqual(spans[0][2:4], (3306, 3527))
        self.assertEqual(spans[1][2:4], (3527, 3748))
        self.assertEqual(spans[2][2:4], (3748, 3848))
        self.assertEqual(spans[3][2:4], (3848, 4102))
        timeline = []
        for _a, _b, ws, we, _k in spans:
            timeline.extend(range(ws, we))
        self.assertEqual(timeline, list(range(3306, 4102)))

    def test_debug_slice_drops_packed_continue_overlap(self):
        self.assertEqual(
            debug_file_slice(3527, 3770, 3527, 3748, 243),
            (0, 221),
        )
        self.assertEqual(
            debug_file_slice(3748, 3848, 3748, 3848, 100),
            (0, 100),
        )
        self.assertEqual(
            debug_file_slice(3527, 3770, 3527, 3748, 221),
            (0, 221),
        )

    def test_mux_duration_covers_continue_write_of_221_frames(self):
        self.assertLess(float(f"{221 / 24:.6f}") * 24, 221)
        self.assertGreaterEqual(audio_mux_duration(221, 24) * 24, 221)
        self.assertGreaterEqual(audio_mux_duration(100, 24) * 24, 100)

    def test_runs_that_fit_max_share_one_pass(self):
        n = 400
        need = np.zeros(n, dtype=bool)
        need[10:80] = True
        need[100:170] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 10)
        self.assertEqual(refine[0][1], 170)
        self.assertLessEqual(refine[0][2], 243)

    def test_jobs_count_h3_passes_not_copy_gaps(self):
        n = 400
        need = np.zeros(n, dtype=bool)
        need[50:120] = True
        jobs = pack_refine_jobs(need, n, 243, overlap=17)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "refine")
        self.assertEqual(jobs[0]["copy_start"], 50)
        self.assertEqual(jobs[0]["start"], 50)
        self.assertEqual(jobs[0]["end"], 120)
        self.assertEqual(jobs[0]["tail_start"], 120)
        self.assertEqual(jobs[0]["tail_end"], 120)
        self.assertEqual(job_hold(jobs, 0, 17), 0)

    def test_far_apart_jobs_stay_two_passes(self):
        n = 800
        need = np.zeros(n, dtype=bool)
        need[10:80] = True
        need[400:470] = True
        jobs = pack_refine_jobs(need, n, 243, overlap=17)
        refine = [j for j in jobs if j["kind"] == "refine"]
        self.assertEqual(len(refine), 2)
        self.assertEqual(refine[0]["end"], 80)
        self.assertEqual(refine[1]["start"], 400)


class TestSustainedVisible(unittest.TestCase):
    def test_brief_flash_is_dropped(self):
        detected = np.zeros(48, dtype=bool)
        detected[10:16] = True
        keep = sustained_visible(detected, 24.0)
        self.assertFalse(bool(keep.any()))

    def test_half_second_is_kept(self):
        detected = np.zeros(48, dtype=bool)
        detected[10:22] = True
        keep = sustained_visible(detected, 24.0)
        self.assertEqual(MIN_VISIBLE_SEC, 0.5)
        self.assertTrue(np.all(keep[10:22]))
        self.assertFalse(bool(keep[:10].any()))
        self.assertFalse(bool(keep[22:].any()))

    def test_one_frame_gap_splits_runs(self):
        detected = np.zeros(48, dtype=bool)
        detected[0:10] = True
        detected[11:23] = True
        keep = sustained_visible(detected, 24.0)
        self.assertFalse(bool(keep[:11].any()))
        self.assertTrue(np.all(keep[11:23]))

    def test_brief_flash_does_not_pack_a_shot(self):
        n = 200
        detected = np.zeros(n, dtype=bool)
        detected[50:56] = True
        need = sustained_visible(detected, 24.0)
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17, breaks=breaks)
        self.assertTrue(all(s[3] == "copy" for s in segs))

    def test_half_second_face_packs_the_shot(self):
        n = 200
        detected = np.zeros(n, dtype=bool)
        detected[50:62] = True
        need = sustained_visible(detected, 24.0)
        breaks = np.zeros(n, dtype=bool)
        breaks[0] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17, breaks=breaks)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 1)
        self.assertEqual(refine[0][0], 0)
        self.assertEqual(refine[0][1], n)

    def test_video_refine_gates_sampling_on_uninterrupted_visible(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "face_refine", "video_refine.py")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("sustained_visible(detected_all, fps, MIN_VISIBLE_SEC)", text)
        self.assertIn('"min_visible_sec"', text)


class TestSeamlessLoopPack(unittest.TestCase):
    def test_wraps_start_and_end_as_one_clip(self):
        n = 400
        need = np.zeros(n, dtype=bool)
        need[:80] = True
        need[320:] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17, loop=True)
        loop = [s for s in segs if s[3] == "loop"]
        self.assertEqual(len(loop), 1)
        tail_start, head_end, grid, _kind = loop[0]
        self.assertEqual(tail_start, 320)
        self.assertEqual(head_end, 80)
        self.assertEqual(loop_span_len(tail_start, head_end, n), 160)
        self.assertEqual(grid, align_h3_frames(160))
        covered = set()
        for start, end, _g, kind in segs:
            if kind == "loop":
                covered.update(range(start, n))
                covered.update(range(0, end))
            else:
                covered.update(range(start, end))
        self.assertEqual(covered, set(range(n)))
        self.assertFalse(any(s[3] == "refine" and (s[0] < 80 or s[1] > 320) for s in segs))

    def test_loop_off_keeps_two_refine_windows(self):
        n = 400
        need = np.zeros(n, dtype=bool)
        need[:80] = True
        need[320:] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17, loop=False)
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(len(refine), 2)
        self.assertFalse(any(s[3] == "loop" for s in segs))

    def test_whole_clip_under_max_rotates_the_join(self):
        n = 200
        need = np.ones(n, dtype=bool)
        segs = pack_refine_chunks(need, n, 243, overlap=17, loop=True)
        loop = [s for s in segs if s[3] == "loop"]
        self.assertEqual(len(loop), 1)
        self.assertEqual(loop[0][0], 100)
        self.assertEqual(loop[0][1], 100)
        self.assertEqual(loop_span_len(loop[0][0], loop[0][1], n), n)
        self.assertEqual(sum(1 for s in segs if s[3] == "refine"), 0)

    def test_one_end_wraps_join_with_context(self):
        n = 200
        need = np.zeros(n, dtype=bool)
        need[:80] = True
        segs = pack_refine_chunks(need, n, 243, overlap=17, loop=True)
        loop = [s for s in segs if s[3] == "loop"]
        self.assertEqual(len(loop), 1)
        tail_start, head_end, _g, _kind = loop[0]
        self.assertEqual(head_end, 80)
        self.assertEqual(tail_start, n - CHUNK_OVERLAP)
        self.assertFalse(any(s[3] == "refine" and s[0] == 0 for s in segs))

    def test_long_clip_straddles_join_inside_max_chunk(self):
        n = 500
        need = np.ones(n, dtype=bool)
        segs = pack_refine_chunks(need, n, 243, overlap=17, loop=True)
        loop = [s for s in segs if s[3] == "loop"]
        self.assertEqual(len(loop), 1)
        tail_start, head_end, grid, _kind = loop[0]
        self.assertEqual(loop_span_len(tail_start, head_end, n), 243 - 2 * 17)
        self.assertEqual(grid, 243)
        self.assertLess(head_end, tail_start)

    def test_adjacent_maskvid_shots_still_wrap_the_join(self):
        n = 1020
        need = np.ones(n, dtype=bool)
        br = np.zeros(n, dtype=bool)
        br[0] = True
        br[956] = True
        segs = pack_refine_chunks(need, n, 243, overlap=22, loop=True, breaks=br)
        loop = [s for s in segs if s[3] == "loop"]
        self.assertEqual(len(loop), 1)
        tail_start, head_end, grid, _kind = loop[0]
        self.assertEqual(loop_span_len(tail_start, head_end, n), 243 - 2 * 22)
        self.assertEqual(grid, 243)
        self.assertLess(head_end, tail_start)
        self.assertFalse(any(s[3] == "refine" and s[0] == 0 for s in segs))
        self.assertFalse(any(s[3] == "refine" and s[1] == n for s in segs))
        refine = [s for s in segs if s[3] == "refine"]
        self.assertEqual(refine[0][0], head_end)
        self.assertEqual(refine[-1][1], tail_start)
        self.assertEqual(segment_hold(segs, len(segs) - 2, 22), 22)

    def test_circular_smooth_matches_at_join(self):
        n = 40
        vals = np.linspace(0.0, 10.0, n)
        vals[-1] = 0.2
        br = np.zeros(n, dtype=bool)
        br[0] = True
        linear = smooth_per_shot(vals, br, 9)
        looped = smooth_per_shot(vals, br, 9, loop=True)
        self.assertGreater(
            abs(float(linear[0] - linear[-1])),
            abs(float(looped[0] - looped[-1])),
        )


class TestCloseupWeight(unittest.TestCase):
    def test_small_face_is_full_paste(self):
        w = closeup_paste_weight([40.0], 768, 0.28)
        self.assertGreater(float(w[0]), 0.99)

    def test_at_skip_frac_is_zero(self):
        w = closeup_paste_weight([0.28 * 768], 768, 0.28)
        self.assertLess(float(w[0]), 0.01)

    def test_ramp_is_between(self):
        w = closeup_paste_weight([0.25 * 768], 768, 0.28)
        self.assertGreater(float(w[0]), 0.01)
        self.assertLess(float(w[0]), 0.99)

    def test_skip_chunk_when_all_close(self):
        self.assertTrue(chunk_is_all_closeup([0.0, 0.0], [True, True]))
        self.assertFalse(chunk_is_all_closeup([0.0, 0.5], [True, True]))
        self.assertTrue(chunk_is_all_closeup([0.0, 0.5], [False, False]))
        self.assertTrue(chunk_is_all_closeup([0.0, 0.04], [True, True]))

    def test_gate_is_binary_with_hysteresis(self):
        src_h = 960.0
        skip = 0.2
        h = np.concatenate([
            np.full(10, 0.12 * src_h),
            np.full(10, 0.25 * src_h),
            np.full(10, 0.16 * src_h),
            np.full(10, 0.10 * src_h),
        ])
        g = closeup_paste_gate(h, src_h, skip, ramp=0.06)
        self.assertTrue(np.all(g[:10] == 1.0))
        self.assertTrue(np.all(g[10:20] == 0.0))
        self.assertTrue(np.all(g[20:30] == 0.0))
        self.assertTrue(np.all(g[30:] == 1.0))
        self.assertTrue(set(g.tolist()) <= {0.0, 1.0})


class TestDetailMatch(unittest.TestCase):
    def test_softer_h3_is_not_blurred(self):
        self.assertAlmostEqual(float(sharpness_match_amount(0.5, 1.0)), 0.0)

    def test_sharper_h3_is_blurred(self):
        self.assertAlmostEqual(float(sharpness_match_amount(2.0, 0.5)), 0.75)
        self.assertAlmostEqual(float(sharpness_match_amount(2.0, 0.5, amount=0.0)), 0.0)


class TestFaceLock(unittest.TestCase):
    def test_follow_puts_face_at_crop_center(self):
        n = 8
        cx = np.linspace(300.0, 500.0, n)
        cy = np.full(n, 400.0)
        sz = np.full(n, 80.0)
        br = shot_breaks_from_tracks(cx, cy, sz)
        out, cx_s, cy_s, sz_s = follow_face_boxes(
            cx, cy, sz, 1.5, 1920, 1080, 1.0, br, pos_window=1, size_window=1,
        )
        for i, b in enumerate(out):
            self.assertAlmostEqual(b[0] + b[2] * 0.5, cx_s[i], places=4)
            self.assertAlmostEqual(b[1] + b[3] * 0.5, cy_s[i], places=4)
            self.assertAlmostEqual(b[3], 120.0, places=4)

    def test_size_follows_push_in_without_steps(self):
        n = 30
        sz = np.linspace(80.0, 160.0, n)
        cx = np.full(n, 400.0)
        cy = np.full(n, 400.0)
        br = shot_breaks_from_tracks(cx, cy, sz)
        self.assertEqual(int(br.sum()), 1)
        boxes, _, _, _ = follow_face_boxes(
            cx, cy, sz, 1.5, 1920, 1080, 1.0, br, pos_window=9, size_window=15,
        )
        sides = np.array([b[3] for b in boxes])
        self.assertLess(float(np.max(np.abs(np.diff(sides)))), 8.0)
        self.assertGreater(float(sides[-1]), float(sides[0]) * 1.3)

    def test_causal_size_does_not_see_future_closeup(self):
        sz = np.array([90.0] * 40 + [280.0] * 40)
        br = np.zeros(len(sz), dtype=bool)
        br[0] = True
        two = smooth_per_shot(sz, br, 15)
        causal = smooth_per_shot(sz, br, 15, causal=True)
        self.assertGreater(float(two[39]), 120.0)
        self.assertLess(float(causal[39]), 95.0)

    def test_cut_snaps_position_and_size(self):
        cx = np.array([120.0] * 10 + [800.0] * 10)
        cy = np.array([120.0] * 10 + [700.0] * 10)
        sz = np.array([80.0] * 10 + [40.0] * 10)
        br = shot_breaks_from_tracks(cx, cy, sz)
        self.assertTrue(bool(br[10]))
        boxes, _, _, _ = follow_face_boxes(
            cx, cy, sz, 1.5, 1920, 1080, 1.0, br, pos_window=9, size_window=15,
        )
        self.assertGreater(abs(boxes[10][0] - boxes[9][0]), 200.0)
        self.assertGreater(abs(boxes[9][3] - boxes[10][3]), 20.0)
        self.assertLess(abs(boxes[5][0] - boxes[0][0]), 30.0)

    def test_smooth_does_not_blend_across_cut(self):
        vals = np.array([10.0] * 8 + [200.0] * 8)
        br = np.zeros(16, dtype=bool)
        br[0] = br[8] = True
        sm = smooth_per_shot(vals, br, window=9)
        self.assertLess(float(sm[7]), 40.0)
        self.assertGreater(float(sm[8]), 170.0)


class TestDenoiseRamp(unittest.TestCase):
    def test_range_follows_skip_frac(self):
        lo, hi = denoise_px_range(768, 0.2)
        self.assertAlmostEqual(hi, 153.6, places=1)
        self.assertLess(lo, 50)

    def test_small_face_keeps_full_strength(self):
        lo, hi = denoise_px_range(768, 0.2)
        s = per_frame_strength([62.0], lo, hi, 1.0, 0.0)
        self.assertGreater(float(s[0]), 0.9)

    def test_at_skip_frac_strength_is_zero(self):
        lo, hi = denoise_px_range(768, 0.2)
        s = per_frame_strength([hi], lo, hi, 1.0, 0.0)
        self.assertLess(float(s[0]), 0.02)

    def test_no_paste_when_crop_downscales(self):
        s = np.ones(1)
        w = refine_paste_weight([500.0], 768, 0.5, 1.2, 512, s)
        self.assertLess(float(w[0]), 0.01)

    def test_no_paste_when_denoise_is_zero(self):
        w = refine_paste_weight([80.0], 768, 0.28, 2.5, 768, [0.0])
        self.assertLess(float(w[0]), 0.01)


class TestFaceTokenInpaint(unittest.TestCase):
    def test_ellipse_covers_full_face_not_lower_half(self):
        rect = (128.0, 128.0, 256.0, 256.0)
        m = face_ellipse_mask(512, 512, [rect], dilation=0)[0]
        cx, cy = 256, 256
        self.assertGreater(float(m[cy, cx]), 0.99)
        self.assertGreater(float(m[cy - 80, cx]), 0.99)
        self.assertGreater(float(m[cy + 80, cx]), 0.99)
        self.assertLess(float(m[8, 8]), 0.01)
        self.assertLess(float(m[500, 500]), 0.01)

    def test_token_snap_face_vs_background(self):
        rect = (4.0, 4.0, 20.0, 20.0)
        pixel = face_ellipse_mask(64, 64, [rect] * 5, dilation=0)
        lat = reduce_mask_h3(pixel, 2, 4, 4)
        self.assertEqual(lat.shape, (1, 1, 2, 4, 4))
        self.assertGreater(float(lat[0, 0, 0, 0, 0]), 0.99)
        self.assertGreater(float(lat[0, 0, 0, 1, 1]), 0.99)
        self.assertLess(float(lat[0, 0, 0, 3, 3]), 0.01)
        self.assertLess(float(lat[0, 0, 1, 3, 3]), 0.01)

    def test_strength_zero_clears_face_tokens(self):
        rect = (16.0, 16.0, 32.0, 32.0)
        pixel = face_ellipse_mask(64, 64, [rect] * 5, dilation=0)
        lat = reduce_mask_h3(pixel, 2, 4, 4, strength=np.zeros(5))
        self.assertLess(float(lat.max()), 0.01)

    def test_undetected_frame_is_zero(self):
        rect = (16.0, 16.0, 32.0, 32.0)
        lat = face_token_video_mask(
            64, 64, [rect] * 5, 2, 4, 4,
            strength=np.ones(5), detected=[False] * 5, dilation=0,
        )
        self.assertLess(float(lat.max()), 0.01)

    def test_audio_companion_is_zeros(self):
        video = np.ones((1, 1, 2, 4, 4), dtype=np.float32)
        v, a = pack_av_noise_mask(video, (1, 32, 2, 40))
        self.assertEqual(v.shape, video.shape)
        self.assertTrue(np.allclose(v, 1.0))
        self.assertEqual(a.shape, (1, 32, 2, 40))
        self.assertTrue(np.allclose(a, 0.0))

    def test_h3_groups_22_frames(self):
        groups = h3_frame_groups(22, 7)
        self.assertEqual(len(groups), 7)
        self.assertEqual(groups[0], (0, 1))
        self.assertEqual(groups[-1][1], 22)
        covered = []
        for a, b in groups:
            covered.extend(range(a, b))
        self.assertEqual(covered[0], 0)
        self.assertEqual(covered[-1], 21)

    def test_h3_steps_covering_context_22(self):
        self.assertEqual(h3_steps_covering(22), 7)
        self.assertEqual(h3_steps_covering(243), h3_latent_t(243))
        self.assertEqual(h3_steps_covering(243) - h3_steps_covering(221), 7)

    def test_overlap_freeze_clears_head(self):
        scale = overlap_freeze_scale(72, 7, soft_steps=2)
        self.assertEqual(scale.shape[0], 72)
        self.assertLess(float(scale[0]), 0.01)
        self.assertLess(float(scale[4]), 0.01)
        self.assertGreater(float(scale[6]), 0.0)
        self.assertLess(float(scale[6]), 1.0)
        self.assertGreater(float(scale[7]), 0.99)

    def test_canvas_rect_maps_into_crop(self):
        sx, sy, sw, sh = canvas_rect_to_source(
            (100.0, 50.0, 200.0, 200.0), (25.0, 25.0, 50.0, 50.0), 100, 100,
        )
        self.assertAlmostEqual(sx, 150.0)
        self.assertAlmostEqual(sy, 100.0)
        self.assertAlmostEqual(sw, 100.0)
        self.assertAlmostEqual(sh, 100.0)

    def test_latent_mask_repeats_across_h3_group(self):
        token = np.zeros((1, 1, 2, 4, 4), dtype=np.float32)
        token[0, 0, 0] = 1.0
        frames = latent_mask_to_frames(token, 5, 64, 64)
        self.assertEqual(frames.shape, (5, 64, 64))
        self.assertGreater(float(frames[0].mean()), 0.99)
        self.assertLess(float(frames[1].mean()), 0.01)

    def test_h3_latent_t_243(self):
        self.assertEqual(h3_latent_t(243), 72)

    def test_face_rect_not_assumed_centered(self):
        crop = (100.0, 100.0, 200.0, 200.0)
        r = face_rect_in_canvas(crop, 150.0, 220.0, 40.0, 80.0, 100, 100)
        self.assertAlmostEqual(r[0], 15.0)
        self.assertAlmostEqual(r[1], 40.0)
        self.assertAlmostEqual(r[2], 20.0)
        self.assertAlmostEqual(r[3], 40.0)


class TestHoldTeleportPlan(unittest.TestCase):
    def test_scene_cut_jumps_instead_of_easing(self):
        n = 40
        H, W = 360, 640
        cx = np.array([80.0] * 20 + [560.0] * 20)
        cy = np.array([80.0] * 20 + [280.0] * 20)
        sz = np.array([80.0] * 20 + [40.0] * 20)
        fw = sz.copy()
        boxes, _info = plan_hold_teleports(
            H, W, cx, cy, fw, sz, crop_factor=2.5, aspect=1.0, seamless_loop=False,
        )
        xs = np.array([b[0] for b in boxes])
        ys = np.array([b[1] for b in boxes])
        hs = np.array([b[3] for b in boxes])
        jump = abs(xs[20] - xs[19]) + abs(ys[20] - ys[19])
        eased = abs(xs[10] - xs[0]) + abs(ys[10] - ys[0])
        self.assertGreater(jump, 200.0)
        self.assertLess(eased, 80.0)
        self.assertGreater(float(hs[:20].mean()), float(hs[20:].mean()) * 1.3)
        fitted = [fit_box_to_aspect(boxes[i], W, H, 1.0) for i in range(n)]
        for b in fitted:
            self.assertAlmostEqual(b[2], b[3], delta=1.0)
            self.assertLessEqual(b[2], W + 1e-6)
            self.assertLessEqual(b[3], H + 1e-6)


class TestFitBoxToAspect(unittest.TestCase):
    def test_widescreen_source_box_becomes_square_for_square_canvas(self):
        box = fit_box_to_aspect((0.0, 0.0, 1920.0, 1080.0), 1920, 1080, 1.0)
        self.assertAlmostEqual(box[2], box[3], places=4)
        self.assertAlmostEqual(box[2], 1080.0, places=4)
        self.assertGreaterEqual(box[0], 0.0)
        self.assertLessEqual(box[0] + box[2], 1920.0 + 1e-6)

    def test_already_square_stays_square(self):
        box = fit_box_to_aspect((100.0, 80.0, 200.0, 200.0), 1920, 1080, 1.0)
        self.assertAlmostEqual(box[2], 200.0)
        self.assertAlmostEqual(box[3], 200.0)


class TestPngSequencePipeline(unittest.TestCase):
    def test_video_refine_reads_and_writes_png_folders(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "face_refine", "video_refine.py")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("class _ImageSeqFrames", text)
        self.assertIn("def _open_source", text)
        self.assertIn("_write_png_range", text)
        self.assertIn(":08d}.png", text)
        self.assertIn("_delete_png_from", text)
        self.assertNotIn("_mux_chunk", text)
        self.assertNotIn("torchaudio.save", text)
        self.assertNotIn("dest = None if file_mode else source", text)
        self.assertIn("_source_fingerprint", text)
        self.assertIn('RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")', text)
        self.assertIn("def _source_media_path", text)
        self.assertIn("_empty_audio()", text)
        self.assertIn("seamless_loop", text)
        self.assertIn('kind == "loop"', text)
        self.assertIn('"loop_wrap"', text)
        self.assertIn("loop_end_latent", text)
        self.assertIn("_freeze_overlap_video_tail", text)


if __name__ == "__main__":
    unittest.main()
