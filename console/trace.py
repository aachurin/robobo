import re
import os
import inspect
import cv2
import settings
from datetime import datetime


TRACE_ENABLED = False


class Trace:
    def __init__(self):
        self.enabled = False
        self.suppressed = []

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def suppress(self, item):
        self.suppressed.append(item)

    def trace(self, op, sample, match, trace_frame=0):
        if not self.enabled:
            return False
        if match in self.suppressed:
            return False
        sample = sample.copy()
        os.makedirs(settings.TRACE_DIR, exist_ok=True)
        if match:
            cv2.rectangle(sample, (match.left + 2, match.top + 2), (match.right - 2, match.bottom - 2), 0, 2)
            cv2.rectangle(sample, (match.left, match.top), (match.right, match.bottom), 255, 2)
        stack = inspect.stack()[1: trace_frame + 2]
        fi = stack[-1]
        path = os.path.splitext(fi.filename)[0]
        module_name = os.path.basename(path)
        time_prefix = datetime.now().strftime("%H_%M_%S_%f")[:-3]
        funcs = "--".join("%s_%s" % (fi.function, fi.lineno) for fi in reversed(stack))
        name = (
            time_prefix,
            module_name,
            funcs,
            op
        )
        match_name = match.name.replace("/", "_")
        if len(match_name) > 40:
            match_name = match_name[:37] + "..."
        name += ("<" + match_name + ">",)
        image_name = "--".join(name) + ".png"
        cv2.imwrite(os.path.join(settings.TRACE_DIR, image_name), sample)
        return True


trace = Trace()
