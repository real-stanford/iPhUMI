import os
from omegaconf import DictConfig
import json
import numpy as np
from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_aligned_frame_times,
    get_demonstration_sides_present,
    get_demonstration_property,
    get_demonstration_main_video_path,
    get_demonstration_frame_times,
)
from iphumi.common.timecode_util import datetime_fromisoformat
from dataclasses import dataclass
from typing import List
import cv2
from tqdm import tqdm
import imageio.v3 as iio


@dataclass
class Task:
    name: str
    start_idx: int  # aligned frame index
    end_idx: int    # aligned frame index


def _wrap_text(text, font, font_scale, thickness, max_width):
    words = text.split(' ')
    lines = []
    current = ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        (w, _), _ = cv2.getTextSize(candidate, font, font_scale, thickness)
        if w <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def pad_subtasks(tasks: List[Task], padding_seconds: float, aligned_fps: float):
    """Pad the subtasks by a fixed amount of time before the start. Mutates `tasks` in place."""
    for task in tasks:
        new_start = int(task.start_idx - padding_seconds * aligned_fps)
        new_start = max(0, new_start)
        task.start_idx = new_start


def _get_label_type(demonstration_dir: str, side: str) -> str:
    try:
        return get_demonstration_property(demonstration_dir, side, 'labelType')
    except KeyError:
        return 'None'


def _get_is_voice_host(demonstration_dir: str, side: str) -> bool:
    try:
        return get_demonstration_property(demonstration_dir, side, 'isVoiceHost')
    except KeyError:
        return False


def _select_task_side(demonstration_dir: str) -> str:
    sides_present = get_demonstration_sides_present(demonstration_dir)
    labelable_sides = [side for side in sides_present if _get_label_type(demonstration_dir, side) != 'None']

    # For Narration mode exactly one side is the voice host — use it as ground truth
    voice_host_sides = [side for side in labelable_sides if _get_is_voice_host(demonstration_dir, side)]
    if len(voice_host_sides) == 1:
        return voice_host_sides[0]

    # For Predefined (or single-device) all sides have identical tasks; prefer head > left > right
    preferred_order = ['head', 'left', 'right']
    for side in preferred_order:
        if side in labelable_sides:
            return side

    return sides_present[0]


def identify_tasks(demonstration_dir, cfg: DictConfig) -> List[Task]:
    """Returns a list of Tasks with start/end indices in aligned frame space."""
    side = _select_task_side(demonstration_dir)
    label_type = _get_label_type(demonstration_dir, side)

    if label_type in ('Narration', 'Predefined'):
        tasks = identify_tasks_labeled(demonstration_dir, cfg, side)
    elif label_type == 'None':
        tasks = []
    else:
        raise NotImplementedError

    if cfg.visualize and len(tasks) > 0:
        for target_side in get_demonstration_sides_present(demonstration_dir):
            visualize_tasks(demonstration_dir, tasks, target_side, cfg.output_height)

    return tasks


def identify_tasks_labeled(demonstration_dir, cfg: DictConfig, side: str) -> List[Task]:
    """Identify subtasks and return them with indices in aligned frame space."""
    aligned_times = get_aligned_frame_times(demonstration_dir)
    aligned_ts = np.array([datetime_fromisoformat(t).timestamp() for t in aligned_times])
    aligned_frame_count = len(aligned_ts)

    task_names = get_demonstration_property(demonstration_dir, side, 'taskNames')
    task_start_timestamps = get_demonstration_property(demonstration_dir, side, 'taskStartTimestamps')
    task_end_timestamps = get_demonstration_property(demonstration_dir, side, 'taskEndTimestamps')

    tasks = []
    for i in range(len(task_names)):
        start_ts = datetime_fromisoformat(task_start_timestamps[i]).timestamp()
        end_ts   = datetime_fromisoformat(task_end_timestamps[i]).timestamp()

        start_frame_idx = max(int(np.searchsorted(aligned_ts, start_ts, side='right')) - 1, 0)
        end_frame_idx   = min(int(np.searchsorted(aligned_ts, end_ts,   side='right')) - 1, aligned_frame_count - 1)

        assert start_frame_idx >= 0 and start_frame_idx < aligned_frame_count, \
            f'Invalid start frame index {start_frame_idx}'
        assert end_frame_idx >= 0 and end_frame_idx < aligned_frame_count, \
            f'Invalid end frame index {end_frame_idx}'
        assert end_frame_idx > start_frame_idx, \
            f'End frame index {end_frame_idx} must be greater than start frame index {start_frame_idx}'

        tasks.append(Task(task_names[i], start_frame_idx, end_frame_idx))

    return tasks


def visualize_tasks(demonstration_dir: str, tasks: List[Task], side: str, output_height: int = 360):
    """Draw task labels on the side's RGB video. Tasks are in aligned frame space;
    they are converted to video frame indices here before drawing."""
    aligned_times = get_aligned_frame_times(demonstration_dir)
    aligned_ts = np.array([datetime_fromisoformat(t).timestamp() for t in aligned_times])

    rgb_time_strings = get_demonstration_frame_times(demonstration_dir, side)
    rgb_ts = np.array([datetime_fromisoformat(t).timestamp() for t in rgb_time_strings])

    def to_video_idx(aligned_idx: int) -> int:
        ts = aligned_ts[min(aligned_idx, len(aligned_ts) - 1)]
        return int(np.searchsorted(rgb_ts, ts, side='right')) - 1

    video_tasks = [
        Task(t.name, to_video_idx(t.start_idx), to_video_idx(t.end_idx))
        for t in tasks
    ]

    video_path = get_demonstration_main_video_path(demonstration_dir, side)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    output_width = int(output_height * frame_width / cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    output_path = os.path.join(demonstration_dir, f'{side}_subtasks.mp4')
    frame_idx = 0
    pbar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), leave=False, desc='Visualizing subtasks')

    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            resized_frame = cv2.resize(frame, (output_width, output_height))

            matching_tasks = [t for t in video_tasks if frame_idx >= t.start_idx and frame_idx < t.end_idx]

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8 * output_height / 360
            thickness = max(1, round(2 * output_height / 360))
            lines = []
            for t in matching_tasks:
                lines.extend(_wrap_text(t.name, font, font_scale, thickness, output_width - 10))
            for i, text in enumerate(lines):
                (_, label_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
                cv2.putText(resized_frame, text, (5, 5 + (i + 1) * label_height), font, font_scale, (0, 0, 255), thickness, cv2.LINE_AA)

            out.write(resized_frame[...,::-1], is_batch=False)

            frame_idx += 1
            pbar.update(1)

    pbar.close()
    cap.release()


def auto_label_demo(demonstration_dir, cfg: DictConfig):
    output_path = os.path.join(demonstration_dir, 'labels_aligned.json')

    side = _select_task_side(demonstration_dir)
    tasks = identify_tasks(demonstration_dir, cfg.task_extraction)

    out = {
        'label_source_side': side,
        'tasks': [
            {
                'name': task.name,
                'relative_aligned_start_frame_idx': task.start_idx,
                'relative_aligned_end_frame_idx': task.end_idx,
                'labels': {}
            }
            for task in tasks
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(out, f)


def auto_label(demonstration_iterator, cfg: DictConfig):
    num_processed = 0
    num_skipped = 0
    already_processed = set()
    already_skipped = set()
    for demonstration_dir in demonstration_iterator('demonstration'):
        output_path = os.path.join(demonstration_dir, 'labels_aligned.json')
        if os.path.exists(output_path) and not cfg.overwrite:
            already_skipped.add(demonstration_dir)
            num_skipped += 1
            continue

        print(f'Labeling {demonstration_to_display_string(demonstration_dir)}')

        auto_label_demo(demonstration_dir, cfg)

        already_processed.add(demonstration_dir)
        num_processed += 1

    print(f'\nLabeled {num_processed} demonstrations')
    print(f'Previously processed {num_skipped} demonstrations')
