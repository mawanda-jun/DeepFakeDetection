import json
import os

import cv2
import numpy as np
from torch.utils.data import Dataset, DataLoader
import torch

from custom_exceptions import NoFrames, NoVideo


class VideoDataset(Dataset):
    def __init__(self, metadata_path, window=1, resize=0.5, transform=None, check_path=None):
        """
        Dataset to load videos and extract faces. I hope this class will make the process faster.
        This class will always take all the possible frames from each video.
        :param metadata_path: path to metadata file. It contains the path to all video files
        :param window: defines how many frames to skip between one take and another. 1: 0 frame skip, 2: 1 frame skipped
        :param resize: percentile of resize for frames. Too big frames lead to OOM
        :param transform: transforms for dataset
        :param check_path: path/to/folder where the embeddings has been created. This is useful in order to avoid to
        redo a previously calculated embedding.
        """
        # Load metadata file
        self.metadata = json.load(open(metadata_path, 'r'))
        # Sanitize paths that has already been transformed
        # Take only file name without extension and sort them for more performance
        done = [os.path.basename(x).split('.')[0] for x in os.listdir(check_path)]
        done.sort()
        # Create empty list for key deletion
        delete = []
        # Retrieve list of metadata keys and sort them by file name
        metadata_keys = list(self.metadata.keys())
        metadata_keys.sort(key=lambda x: os.path.basename(x))
        # Check each path in metadata and compare to check_path dir. Each time it finds an element, it does not consider
        # it anymore since it starts from the previous element.
        for p in metadata_keys:
            p_name = os.path.basename(p).split('.')[0]
            if p_name in done[len(delete):]:
                delete.append(p)
        for d in delete:
            self.metadata.pop(d)

        # Define path to all videos to access them with getitem
        self.path_to_all_videos = list(self.metadata.keys())
        # Define window: steps for reading video
        self.window = window
        # Define resize measure for faces. The feature extractor has been pre-trained with 160x160 images, so we are
        # going to keep this dimension
        self.resize = resize
        # Define transforms for Dataset
        self.transform = transform
        # Define list of error path to retrieve later if needed
        self.error_paths = []
        # Define max number of frames to extract from each video. Considering 1 min -> 24fps * 60 sec = 1440
        self.max_v_len = 1440

    def __len__(self):
        return len(self.path_to_all_videos)

    def __getitem__(self, idx):
        try:
            # Create video reader and find length
            video_path = self.path_to_all_videos[idx]

            v_cap = cv2.VideoCapture(video_path)
            v_len = int(v_cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # In case of missing video file just skip and raise exception
            if v_len == 0:
                raise NoVideo(video_path)

            # Define frame height and width to prepare an empty numpy vector
            v_height = int(v_cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * self.resize)
            v_width = int(v_cap.get(cv2.CAP_PROP_FRAME_WIDTH) * self.resize)

            # Prepare emtpy batch of frames
            # frames = np.zeros((batch_size, v_height, v_width, 3), dtype='uint8')
            frames = []

            # Actually extract frames
            for i in range(v_len)[:self.max_v_len]:
                # Select next frame
                _ = v_cap.grab()
                if i % self.window == 0:
                    # Load frame
                    success, frame = v_cap.retrieve()

                    # Skip frame if retrieve is not successful
                    if not success:
                        continue  # TODO: debug how many times it happens

                    # Decode and resize frame
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.resize(frame, (v_width, v_height))

                    # Put frame into batch of frames
                    frames.append(frame)
            if frames:
                return video_path, np.array(frames, dtype='uint8'), self.metadata[video_path]['label']
            # If no frame has been retrieved, raise exception
            else:
                raise NoFrames(video_path)

        # Manage exceptions
        except NoVideo as e:
            print("Video {} not found".format(e))
            self.error_paths.append(e)
            return None
        except NoFrames as e:
            print("Video {} has no frames".format(e))
            self.error_paths.append(e)
            return None


def collate_fn(batch):
    """
    Custom collate function to skip None videos and to manage multiple resolution videos from source
    :param batch:
    :return:
    """
    return CustomBatch(batch)
#     # Filter out None videos (that is, the ones that triggered some custom_exceptions)
#     batch = list(filter(lambda x: x is not None, batch))
#     # Create lists for batch
#     video_paths = []
#     frames = []
#     labels = []
#     for el in batch:
#         video_paths.append(el['video_path'])
#         frames.append(el['frame'])
#         labels.append(el['label'])
#     return {
#         'video_path': video_paths,
#         'frame': frames,
#         'label': labels
#     }


class CustomBatch:
    def __init__(self, data):
        transposed_data = list(zip(*filter(lambda x: x is not None, data)))
        self.video_path = transposed_data[0]
        self.frame = transposed_data[1]
        self.label = transposed_data[2]

    # def pin_memory(self):
    #     self.frame = [torch.tensor(t).pin_memory() for t in self.frame]
    #     return self


if __name__ == '__main__':
    dataset = VideoDataset('C:\\Users\\mawanda\\PyCharmProjects\\DeepFakeCompetition\\data\\train_data')
    dataloader = DataLoader(
        dataset,
        batch_size=2,
        # sampler=Subset[0, 1, 2],
        num_workers=0,
        pin_memory=True
    )
    for batch in dataloader:
        video_paths = batch['video_path']  # List of batch_size paths
        video_frames = batch['frame']  # List of frames: (batch_size, n_frames, height, width, channels)
        labels = batch['label']  # List of labels: FAKE, REAL
        # proof_frame = Image.fromarray(video_frames[0][0].detach().cpu().numpy()).show()
        # print("Video_paths: {}".format(video_paths))
        # print("Video frames: {}".format(video_frames))
        # print("Video label: {}".format(labels))
