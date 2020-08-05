import io
from math import sqrt

import requests
import scaleapi
from PIL import Image


class Checker(object):

    def __init__(self, api_key):
        if not api_key:
            raise Exception('No API key provided')
        self.api_key = api_key
        self.client = scaleapi.ScaleClient(self.api_key)

    def run_checks(self, tasks=[]) -> list:
        checks = []
        for task in tasks:
            occ_check, occ_warns = self._passes_occlusion_check(task, 40)
            stray_check, stray_clicks = self._passes_stray_click_check(task)
            color_check, wrong_colors = self._passes_color_check(task)
            if not occ_check:
                checks += occ_warns
            if not stray_check:
                checks += stray_clicks
            if not color_check:
                checks += wrong_colors

        warnings = {
            'count': len(checks),
            'types': ['occlusion', 'stray_click', 'color'],
            'flagged': checks
        }
        return warnings

    @staticmethod
    def _passes_color_check(task) -> (bool, list):
        """
        Tests if a task containing annotations that have specified a wrong background color
        :param task: A task object containing 1 or more annotations
        :return: A tuple specifying if the task passes the check, and if not, a list of annotations flagged
        """
        warnings = []

        colors = {'white': (255, 255, 255), 'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255)}

        def closest_color(rgb):
            r, g, b = rgb
            color_diffs = []
            for color, code in colors.items():
                cr, cg, cb = code
                color_diff = sqrt(abs(r - cr) ** 2 + abs(g - cg) ** 2 + abs(b - cb) ** 2)
                color_diffs.append((color_diff, color))
            return min(color_diffs)[1]

        def download_image(url, extension):
            r = requests.get(url, timeout=4.0)
            if r.status_code != requests.codes.ok:
                raise Exception('Invalid URL for the image')

            with Image.open(io.BytesIO(r.content)) as im:
                im.save('temp.' + extension)
                return im

        def is_traffic_light(width, height):
            return width / height < 0.55

        for annotation in task.param_dict['response']['annotations']:
            color = annotation['attributes']['background_color']
            if color != 'not_applicable' and annotation['label'] == 'non_visible_face':
                warning = {
                    'type': 'color',
                    'severity': 10,
                    'annotations': [annotation['uuid']],
                    'task': task.id,
                    'explanation': 'Incorrect color labelled for non_visible_face'
                }
                warnings.append(warning)
            elif color == 'not_applicable' and annotation['label'] != 'non_visible_face':
                warning = {
                    'type': 'color',
                    'severity': 10,
                    'annotations': [annotation['uuid']],
                    'task': task.id,
                    'explanation': 'Incorrect object labelled with not_applicable color'
                }
                warnings.append(warning)
            elif annotation['label'] == 'traffic_control_sign' and is_traffic_light(annotation['width'], annotation[
                'height']) and color != 'other':
                warning = {
                    'type': 'color',
                    'severity': 10,
                    'annotations': [annotation['uuid']],
                    'task': task.id,
                    'explanation': 'Traffic light labelled with a color'
                }
                warnings.append(warning)
            elif color in colors:
                image_url = task.param_dict['params']['attachment']
                img_type = image_url.split('.')[-1]
                img = download_image(image_url, img_type)
                img = img.convert('RGB')
                left = annotation['left']
                top = annotation['top']
                right = annotation['width'] + left
                bottom = annotation['height'] + top
                cropped_img = img.crop((left, top, right, bottom))
                present_colors = cropped_img.getcolors()

                if present_colors:
                    found = False
                    colors_found = []
                    for present_color in sorted(present_colors, key=lambda x: x[0], reverse=True)[:2]:
                        colors_found.append(closest_color(present_color[1]))

                        if closest_color(present_color[1]) == color:
                            found = True
                    if not found:
                        warning = {
                            'type': 'color',
                            'severity': 5,
                            'annotations': [annotation['uuid']],
                            'task': task.id,
                            'explanation': 'Potential color issue'
                        }
                        warnings.append(warning)

        return len(warnings) == 0, warnings

    @staticmethod
    def _passes_stray_click_check(task) -> (bool, list):
        """
        Tests if a contractor has made stray or accidental annotations on the task image
        :param task: A task object containing 1 or more annotations
        :return: A tuple specifying if the task passes the check, and if not, a list of annotations flagged
        """
        warnings = []
        for annotation in task.param_dict['response']['annotations']:
            width, height = annotation['width'], annotation['height']
            if (width <= 5 and height <= 5) or (isinstance(width, float) or isinstance(height, float)):
                warning = {
                    'type': 'stray_click',
                    'annotations': [annotation['uuid']],
                    'task': task.id,
                    'severity': 10,
                    'explanation': 'Stray click'
                }
                warnings.append(warning)
        return len(warnings) == 0, warnings

    @staticmethod
    def _passes_occlusion_check(task, threshold) -> (bool, list):
        """
        Tests if there is occlusion for the given annotation, but the contractor has claimed '0%' due to laziness etc.
        :param task: A Task object containing 1 or more annotations to be checked
        :param threshold: An Integer representing the minimum level of occlusion to be flagged as occluded.
        :return: A tuple specifying if the task passes the occlusion check, and if not, a list of annotations flagged
        """

        def occlusion_percentage(annotation1, annotation2):

            a1_x = range(int(annotation1['left']), int(annotation1['left']) + int(annotation1['width']))
            a1_y = range(int(annotation1['top']), int(annotation1['top']) + int(annotation1['height']))
            a2_x = range(int(annotation2['left']), int(annotation2['left']) + int(annotation2['width']))
            a2_y = range(int(annotation2['top']), int(annotation2['top']) + int(annotation2['height']))

            # Get percentage occluded by x side
            max_x = max(max(a1_x), max(a2_x))
            min_x = min(min(a1_x), min(a2_x))
            diff_x = max_x - min_x
            max_y = max(max(a1_y), max(a2_y))
            min_y = min(min(a1_y), min(a2_y))
            diff_y = max_y - min_y
            x_intersection = len(set(a1_x).intersection(a2_x)) / diff_x
            y_intersection = len(set(a1_y).intersection(a2_y)) / diff_y

            occluded = x_intersection > 0 and y_intersection > 0
            return ((x_intersection + y_intersection) / 2) * 100 if occluded else 0

        warnings = []
        annotations = task.param_dict['response']['annotations']
        for index, annotation in enumerate(annotations):
            for secondary_annotation in (annotations[:index] + annotations[index + 1:]):
                if occlusion_percentage(annotation, secondary_annotation) > threshold and (
                        annotation['attributes']['occlusion'] == '0%' and secondary_annotation['attributes'][
                    'occlusion'] == '0%'):
                    warning = {
                        'type': 'occlusion',
                        'severity': 10,
                        'annotations': [annotation['uuid'], secondary_annotation['uuid']],
                        'task': task.id,
                        'explanation': 'Potential for occlusion yet marked as 0%'
                    }
                    warnings.append(warning)

        return len(warnings) == 0, warnings
