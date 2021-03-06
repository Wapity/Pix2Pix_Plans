from rtv.network import RasterToVector
from rtv.ip import *
import torch
from skimage import io, transform
from os import listdir
from os.path import isfile, join
from datetime import datetime
import cv2 as cv2
import string
import itertools

alphabet = string.ascii_lowercase.replace('t', '').replace('n', '')
threshold_text = 0.5   # can adapt


def contains_letter(string):
    for letter in alphabet:
        if letter in string:
            return True
    return False


def dist(x1, x2):
    sommes = [abs(x1[i] - x2[i]) for i in range(len(x1))]
    return sommes


def getter_line(line):
    x, j = [], 0
    counter_points = 0
    for i in range(len(line)):
        if line[i] == "\t":
            if counter_points == 4:
                break
            x.append(float(line[j:i + 1]))
            j = i + 1
            counter_points += 1
    return x


def load_img(path_sample):
    img = io.imread(path_sample)
    if img.shape[2] == 4:
        img[np.where(img[:, :, 3] == 0)] = 255
    img = transform.resize(img, (256, 256))
    img = img[:, :, :3].astype('float32')
    image = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0)
    return img, image


def apply_rtv(img, image, output_prefix, RTV, gap=-1,
              distanceThreshold=-1,
              lengthThreshold=-1,
              heatmapValueThresholdWall=None,
              heatmapValueThresholdDoor=None,
              heatmapValueThresholdIcon=None,):
    output_prefix += '_'
    corner_pred, icon_pred, room_pred = RTV(image)
    corner_pred, icon_pred, room_pred = corner_pred.squeeze(
        0), icon_pred.squeeze(0), room_pred.squeeze(0)
    corner_heatmaps = corner_pred.detach().cpu().numpy()
    icon_heatmaps = torch.nn.functional.softmax(icon_pred,
                                                dim=-1).detach().cpu().numpy()
    room_heatmaps = torch.nn.functional.softmax(room_pred,
                                                dim=-1).detach().cpu().numpy()

    reconstructFloorplan(
        corner_heatmaps[:, :, :NUM_WALL_CORNERS],
        corner_heatmaps[:, :, NUM_WALL_CORNERS:NUM_WALL_CORNERS + 4],
        corner_heatmaps[:, :, -4:],
        icon_heatmaps,
        room_heatmaps,
        output_prefix=output_prefix,
        densityImage=None,
        gt_dict=None,
        gt=False,
        gap=gap,
        distanceThreshold=distanceThreshold,
        lengthThreshold=lengthThreshold,
        debug_prefix='test',
        heatmapValueThresholdWall=heatmapValueThresholdWall,
        heatmapValueThresholdDoor=heatmapValueThresholdWall,  # same threshold here
        heatmapValueThresholdIcon=heatmapValueThresholdWall,  # same threshold here
        enableAugmentation=True)
    dicts = {
        'corner': corner_pred.max(-1)[1].detach().cpu().numpy(),
        'icon': icon_pred.max(-1)[1].detach().cpu().numpy(),
        'room': room_pred.max(-1)[1].detach().cpu().numpy()
    }

    for info in ['corner', 'icon', 'room']:
        cv2.imwrite(
            output_prefix + '.png',
            drawSegmentationImage(dicts[info],
                                  blackIndex=0,
                                  blackThreshold=0.5))


def full_rtv(folder_inputs, folder_outputs, paths, RTV):

    gaps = [1, 3, 5, 7]
    distances = [3, 5, 7]
    lengths = [1, 3, 5, 7]
    heatmaps_wall = [0.01]

    for path_sample in paths:
        img, image = load_img(folder_inputs + path_sample)
        for gap, distanceThreshold, lengthThreshold, heatmapValueThresholdWall in itertools.product(gaps, distances, lengths, heatmaps_wall):
            output_prefix = folder_outputs + path_sample[:-4] + \
                '_gap_{}_dist_{}_length_{}_wall_{}'.format(
                gap, distanceThreshold, lengthThreshold,
                heatmapValueThresholdWall)
            print(output_prefix)
            apply_rtv(img, image, output_prefix, RTV, gap=gap,
                      distanceThreshold=distanceThreshold,
                      lengthThreshold=lengthThreshold,
                      heatmapValueThresholdWall=heatmapValueThresholdWall)

        files = os.listdir(folder_outputs)
        all_txt = [folder_outputs + file for file in files if path_sample[:-4]
                   in file and file.endswith("floorplan.txt")]
        all_lines = [line.replace("\t8", " ").replace("\t6", " ").replace("\t3", " ") for txt in all_txt
                     for line in open(txt, "r") if len(line) > 10]
        all_lines = [line for line in all_lines]

        txt_main_int = list(set([
            line for line in all_lines if not contains_letter(line)]))
        txt_main_str = list(
            set([line for line in all_lines if contains_letter(line)]))

        # sum of masks
        images = np.zeros((256, 256, 3))
        for file in files:
            if file.endswith('result_line.png') and path_sample[:-4] in file:
                images += cv2.imread(os.path.join(folder_outputs, file), 1)
        cv2.imwrite(folder_outputs +
                    path_sample[:-4] + '_sum' + '.png', images)

        for i, line in enumerate(txt_main_int):
            txt_main_int[i] = line[:-5] + \
                "\twall\t" + "1\t" + "1\t" + "\n"

        for i, line in enumerate(txt_main_str):
            txt_main_str[i] = line.replace("\n", "\t\n")

        with open(folder_outputs + path_sample[:-4] + "_sum.txt", "w") as writer_main:
            writer_main.writelines(txt_main_int)
            writer_main.writelines(txt_main_str)


if __name__ == '__main__':

    device = torch.device("cpu")

    RTV = RasterToVector()
    RTV.load_state_dict(
        torch.load('rtv/checkpoints/rtv.pth', map_location=device))

    folder_inputs = 'rtv/rtv_inputs/'
    folder_outputs = 'rtv/rtv_outputs/{}/'.format(
        datetime.now().strftime('%m-%d_%H-%M-%S'))
    os.makedirs(folder_outputs)
    paths = [f for f in listdir(folder_inputs)
             if isfile(join(folder_inputs, f))]

    full_rtv(folder_inputs, folder_outputs, paths, RTV)
