from rtv.network import RasterToVector
from rtv.ip import *
import torch
from skimage import io, transform
from os import listdir
from os.path import isfile, join
from datetime import datetime

RTV = RasterToVector()
RTV.load_state_dict(
    torch.load('rtv/checkpoints/rtv.pth', map_location=torch.device('cpu')))

folder_inputs = 'rtv_inputs/'
folder_outputs = 'rtv_outputs/{}/'.format(
    datetime.now().strftime('%m-%d_%H-%M-%S'))
os.makedirs(folder_outputs)
paths = [f for f in listdir(folder_inputs) if isfile(join(folder_inputs, f))]


def load_img(path_sample):
    img = io.imread(path_sample)
    if img.shape[2] == 4:
        img[np.where(img[:, :, 3] == 0)] = 255
    img = transform.resize(img, (256, 256))
    img = img[:, :, :3].astype('float32')
    minval = np.percentile(img, 2)
    maxval = np.percentile(img, 98)
    img = np.clip(img, minval, maxval)
    img = ((img - minval) / (maxval - minval))
    th = 0.5
    img[np.where(img > th)] = 1.
    img[np.where(img < th)] = 0.
    image = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0)
    return img, image


def apply_rtv(img, image, output_prefix):
    output_prefix += '_'
    corner_pred, icon_pred, room_pred = RTV(image)
    corner_pred, icon_pred, room_pred = corner_pred.squeeze(
        0), icon_pred.squeeze(0), room_pred.squeeze(0)
    corner_heatmaps = corner_pred.detach().cpu().numpy()
    icon_heatmaps = torch.nn.functional.softmax(icon_pred,
                                                dim=-1).detach().cpu().numpy()
    room_heatmaps = torch.nn.functional.softmax(room_pred,
                                                dim=-1).detach().cpu().numpy()
    print(corner_heatmaps.shape, icon_heatmaps.shape, room_heatmaps.shape)
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
        gap=-1,
        distanceThreshold=-1,
        lengthThreshold=-1,
        debug_prefix='test',
        heatmapValueThresholdWall=None,
        heatmapValueThresholdDoor=None,
        heatmapValueThresholdIcon=None,
        enableAugmentation=True)
    dicts = {
        'corner': corner_pred.max(-1)[1].detach().cpu().numpy(),
        'icon': icon_pred.max(-1)[1].detach().cpu().numpy(),
        'room': room_pred.max(-1)[1].detach().cpu().numpy()
    }
    cv2.imwrite(output_prefix + 'image.png', img * 255)
    for info in ['corner', 'icon', 'room']:
        cv2.imwrite(
            output_prefix + info + '.png',
            drawSegmentationImage(dicts[info], blackIndex=0,
                                  blackThreshold=0.5))


for path_sample in paths:
    img, image = load_img(folder_inputs + path_sample)
    output_prefix = folder_outputs + path_sample[:-4]
    apply_rtv(img, image, output_prefix)
