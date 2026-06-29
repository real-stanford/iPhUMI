import argparse
from iphumi.common.replay_buffer_util import print_replay_buffer_umi
from iphumi.common.imagecodecs_numcodecs import register_codecs
register_codecs(verbose=False)

parser = argparse.ArgumentParser(description='View the contents of a replay buffer.')
parser.add_argument('dataset_path', type=str, help='Path to the replay buffer to view.')
parser.add_argument('--vis-frame', action='store_true', help='Save images of the RGB data.')
parser.add_argument('--vis-video', action='store_true', help='Save video of the RGB data.')
parser.add_argument('--vis-tasks', action='store_true', help='Save a video per task of the left and right main cameras horizontally stacked, named by task name.')
parser.add_argument('--load-dataset-in-memory', action='store_true', help='Load the replay buffer into memory instead of keeping it on disk. Faster for small datasets or when saving videos.')
args = parser.parse_args()

print_replay_buffer_umi(args.dataset_path, vis_frame=args.vis_frame, vis_video=args.vis_video, vis_tasks=args.vis_tasks, load_buffer_into_memory=args.load_dataset_in_memory)
