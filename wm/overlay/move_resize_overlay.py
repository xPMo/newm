from threading import Thread
import time

from pywm import PYWM_PRESSED

from pywm.touchpad import (
    SingleFingerMoveGesture,
    TwoFingerSwipePinchGesture,
    GestureListener,
    LowpassGesture
)
from .overlay import Overlay

class MoveOverlay:
    def __init__(self, layout, view):
        self.layout = layout

        self.view = view
        self.original_state = self.layout.state.copy()


        view_state = self.original_state.get_view_state(view._handle)

        self.layout.update(
            self.original_state.copy().replacing_view_state(
                self.view._handle,
                move_origin=(view_state.i, view_state.j)
            ))

        self.last_dx = 0
        self.last_dy = 0

        self._closed = False

    def reset_gesture(self):
        self.last_dx = 0
        self.last_dy = 0

    def on_gesture(self, values):
        if self._closed:
            return
        
        self.layout.state.get_view_state(self.view._handle).i += 4*(values['delta_x'] - self.last_dx)
        self.layout.state.get_view_state(self.view._handle).j += 4*(values['delta_y'] - self.last_dy)
        self.last_dx = values['delta_x']
        self.last_dy = values['delta_y']
        self.layout.damage()

    def close(self):
        self._closed = True

        state = self.layout.state.get_view_state(self.view._handle)
        i, j = state.i, state.j
        fi, fj = round(i), round(j)

        return state.i, state.j, state.w, state.h, fi, fj, state.w, state.h


class ResizeOverlay:
    def __init__(self, layout, view):
        self.layout = layout

        self.view = view
        self.original_state = self.layout.state.copy()

        view_state = self.original_state.get_view_state(view._handle)

        self.layout.update(
            self.original_state.copy().replacing_view_state(
                self.view._handle,
                scale_origin=(view_state.w, view_state.h)
            ))

        self.last_dx = 0
        self.last_dy = 0

        self._closed = False

    def reset_gesture(self):
        self.last_dx = 0
        self.last_dy = 0

    def on_gesture(self, values):
        if self._closed:
            return

        self.layout.state.get_view_state(self.view._handle).w += 4*(values['delta_x'] - self.last_dx)
        self.layout.state.get_view_state(self.view._handle).h += 4*(values['delta_y'] - self.last_dy)
        self.last_dx = values['delta_x']
        self.last_dy = values['delta_y']
        self.layout.damage()

    def close(self):
        self._closed = True

        state = self.layout.state.get_view_state(self.view._handle)
        w, h = state.w, state.h
        fw, fh = round(w), round(h)
        fw = max(1, fw)
        fh = max(1, fh)

        return state.i, state.j, state.w, state.h, state.i, state.j, fw, fh



class MoveResizeOverlay(Overlay, Thread):
    def __init__(self, layout):
        Overlay.__init__(self, layout)
        Thread.__init__(self)

        self.layout.update_cursor(False)

        self.view = self.layout.find_focused_view()

        self.overlay = None

        """
        If move has been finished and we are animating towards final position
            (view initial i, view initial j, view final i, view final j, initial time, finished time)
        """
        self._target_view_pos = None

        """
        If resize has been finished and we are animating towards final size
            (view initial w, view initial h, view final w, view final h, initial time, finished time)
        """
        self._target_view_size = None

        """
        If we are adjusting viewpoint (after gesture finished or during)
            (layout initial i, layout initial j, layout final i, layout final j, initial time, finished time)
        """
        self._target_layout_pos = None
        
        self._wants_close = False
        self.start()

    def _try_set_view_state(self, **kwargs):
        try:
            view_state = self.layout.state.get_view_state(self.view._handle)
            for k, v in kwargs.items():
                view_state.__dict__[k] = v
        except Exception as e:
            print("Cannot animate view")

    def run(self):
        running = True
        while running:
            t = time.time()

            in_prog = False
            if self._target_view_pos is not None:
                in_prog = True
                ii, ij, fi, fj, it, ft = self._target_view_pos
                if t > ft:
                    self._try_set_view_state(i=fi, j=fj, move_origin=(None, None))
                    self._target_view_pos = None
                else:
                    perc = (t-it)/(ft-it)
                    self._try_set_view_state(i=ii + perc*(fi-ii), j=ij + perc*(fj-ij))
                self.layout.damage()


            if self._target_view_size is not None:
                in_prog = True
                iw, ih, fw, fh, it, ft = self._target_view_size
                if t > ft:
                    self._try_set_view_state(w=fw, h=fh, scale_origin=(None, None))
                    self._target_view_size = None
                else:
                    perc = (t-it)/(ft-it)
                    self._try_set_view_state(w=iw + perc*(fw-iw), h=ih + perc*(fh-ih))
                self.layout.damage()

            if self._target_layout_pos is not None:
                in_prog = True
                ii, ij, fi, fj, it, ft = self._target_layout_pos
                if t > ft:
                    self.layout.state.i = fi
                    self.layout.state.j = fj
                    self._target_layout_pos = None
                else:
                    perc = (t-it)/(ft-it)
                    self.layout.state.i=ii + perc*(fi-ii)
                    self.layout.state.j=ij + perc*(fj-ij)
                self.layout.damage()
            elif self.overlay is not None:
                try:
                    view_state = self.layout.state.get_view_state(self.view._handle)
                    i, j, w, h= view_state.i, view_state.j, view_state.w, view_state.h
                    i, j, w, h = round(i), round(j), round(w), round(h)

                    fi, fj = self.layout.state.i, self.layout.state.j

                    if i + w > fi + self.layout.state.size:
                        fi = i + w - self.layout.state.size

                    if j + h > fj + self.layout.state.size:
                        fj = j + h - self.layout.state.size

                    if i < fi:
                        fi = i

                    if j < fj:
                        fj = j


                    if i != self.layout.state.i or j != self.layout.state.j:
                        self._target_layout_pos = (self.layout.state.i, self.layout.state.j, fi, fj, time.time(), time.time() + .3)

                except Exception:
                    print("Cannot read view state")


            if not in_prog and self._wants_close:
                running = False

            time.sleep(1. / 120.)
        self.layout.exit_overlay()

    def on_gesture(self, gesture):

        if isinstance(gesture, TwoFingerSwipePinchGesture):
            if self._target_view_size is not None:
                return

            self.overlay = ResizeOverlay(self.layout, self.view)
            LowpassGesture(gesture).listener(GestureListener(
                self.overlay.on_gesture,
                self.finish
            ))
            return True

        if isinstance(gesture, SingleFingerMoveGesture):
            if self._target_view_pos is not None:
                return

            self.overlay = MoveOverlay(self.layout, self.view)
            LowpassGesture(gesture).listener(GestureListener(
                self.overlay.on_gesture,
                self.finish
            ))
            return True

        return False


    def finish(self):
        if self.overlay is not None:
            ii, ij, iw, ih, fi, fj, fw, fh = self.overlay.close()
            if ii != fi or ij != fj:
                self._target_view_pos = (ii, ij, fi, fj, time.time(), time.time() + .3)
            if iw != fw or iw != fw:
                self._target_view_size = (iw, ih, fw, fh, time.time(), time.time() + .3)


            """
            TODO: Layout pos adjustment
            """

        if not self.layout.modifiers & self.layout.mod:
            self.close()

    def on_motion(self, time_msec, delta_x, delta_y):
        return False

    def on_axis(self, time_msec, source, orientation, delta, delta_discrete):
        return False

    def on_key(self, time_msec, keycode, state, keysyms):
        if state != PYWM_PRESSED and self.layout.mod_sym in keysyms:
            self.close()

    def on_modifiers(self, modifiers):
        return False

    def close(self):
        self._wants_close = True

    def _exit_transition(self):
        self.layout.update_cursor(True)
        return self.layout.state.replacing_view_state(
            self.view._handle,
            scale_origin=(None, None), move_origin=(None, None)), .3