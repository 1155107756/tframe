from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import re
import six

import numpy as np

from PIL import Image as Image_
from PIL import ImageTk

from tframe import console
from tframe import TFData
from tframe import pedia

from tframe.utils.tfdata import load_mnist

try:
  import tkinter as tk
  from tkinter import filedialog
  console.show_status('tkinter imported')
except:
  # Tkinter in python 2.X may work weired, thus python 3.X is recommended.
  import Tkinter as tk
  import tkFileDialog as filedialog
  console.show_status('Tkinter imported')


class ImageViewer(object):
  """Image Viewer for TFData"""

  MIN_WIDTH = 260
  MIN_HEIGHT = 260

  def __init__(self, dataset=None):
    # Variables
    self.filename = None
    self.image_height = self.MIN_HEIGHT
    self.image_width = self.MIN_WIDTH

    # Create interface root
    self.form = tk.Tk()

    # Create frames and widgets
    self.top_frame = tk.Frame(self.form, bg='white')
    self.canvas = tk.Canvas(self.form, bg='white', highlightthickness=0)
    self.bottom_frame = tk.Frame(self.form, bg='white')
    self.image_info = tk.Label(self.top_frame, bd=0, bg='white')
    self.details = tk.Label(self.bottom_frame, bd=0, bg='white')

    # Create layout
    self._create_layout()

    # Data set
    self.dataset = None
    self.labels = None
    self.set_data(dataset)
    self.update_title()

  # region : Properties

  @property
  def screen_size(self):
    assert isinstance(self.form, tk.Tk)
    return self.form.winfo_screenheight(), self.form.winfo_screenwidth()

  @property
  def height(self):
    label_height = (self.top_frame.winfo_height() +
                    self.bottom_frame.winfo_height())
    return label_height + self.image_height

  @property
  def width(self):
    return self.image_width

  @property
  def lastdir(self):
    if self.filename is None:
      return os.getcwd()
    else:
      paths = re.split(r'/|\\]', self.filename)
      return '/'.join(paths[:-1])

  # endregion : Properties

  # region : Public Methods

  def set_data(self, dataset):
    if dataset is not None:
      # If a path is given
      if isinstance(dataset, six.string_types):
        dataset = TFData.load(dataset)
      if not isinstance(dataset, TFData):
        raise TypeError('Data set must be an instance of TFData')
      dataset.set_cursor(0)
      self.dataset = dataset
      self.labels = self.dataset.scalar_labels
      console.show_status('Data set set to ImageViewer')

    # Refresh image viewer
    self.refresh()

  def show(self):
    assert isinstance(self.form, tk.Tk)
    self.form.after(20, self.move_to_center)
    self.form.mainloop()

  # endregion : Public Methods

  # region : Private Methods

  def _create_layout(self):
    # Form properties
    self.form.title('Image Viewer')
    # self.form.resizable(width=False, height=False)

    # Widgets
    self.top_frame.pack(side=tk.TOP, fill=tk.X)
    self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
    self.canvas.pack(side=tk.TOP, fill=tk.BOTH)

    self.image_info.pack(side=tk.LEFT, padx=5)
    self.details.pack(side=tk.LEFT, padx=5)

    # Key binds
    self.form.bind('<Key>', self._on_key_press)
    self.form.bind('<Control-s>', self.save_dataset)
    self.form.bind('<Control-l>', self.load_dataset)

  def move_to_center(self):
    sh, sw = self.screen_size
    x = sw // 2 - self.width // 2
    y = sh // 2 - self.height // 2
    self.form.geometry('{}x{}+{}+{}'.format(self.width, self.height, x, y))

  def _on_key_press(self, event):
    assert isinstance(event, tk.Event)

    flag = False
    if event.keysym == 'Escape':
      self.form.quit()
    elif event.keysym == 'j':
      flag = self.move_cursor(1)
    elif event.keysym == 'k':
      flag = self.move_cursor(-1)
    elif event.keysym == 'quoteleft':
      for k in self.__dict__.keys():
        item = self.__dict__[k]
        if isinstance(item, tk.Widget) or k == 'form':
          str = '[{}] {}: {}x{}'.format(
            item.__class__, k, item.winfo_height(), item.winfo_width())
          console.show_status(str)
    elif event.keysym == 'space':
      self.resize()
    else:
      # console.show_status(event.keysym)
      pass

    # If needed, refresh image viewer
    if flag:
      self.refresh()

  def move_cursor(self, step):
    assert step in [-1, 1]
    flag = False
    if self.dataset is not None:
      assert isinstance(self.dataset, TFData)
      if self.dataset.sample_num == 0:
        return False
      self.dataset.move_cursor(step)
      flag = True

    return flag

  def refresh(self):
    self.update_info()
    self.update_image()
    self.update_details()
    self.resize()

  def update_title(self):
    filename = 'New Data Set'
    if self.filename is not None:
      # Hide directory information
      paths = re.split(r'/|\\]', self.filename)
      filename = paths[-1]
      # Hide extension 'cause it provides no information
      filename = filename[:-4]
    title = 'Image Viewer - {}'.format(filename)
    self.form.title(title)

  def update_info(self):
    if self.dataset is not None:
      assert isinstance(self.dataset, TFData)
      cursor = self.dataset.cursor
      info = ''
      if self.labels is not None:
        info = 'Label: {}'.format(self.labels[cursor])
      self.image_info.config(fg='DodgerBlue4', text='[{} / {}] {}'.format(
        cursor + 1, self.dataset.sample_num, info))
    else:
      self.image_info.config(text='No data set found', fg='grey')

  def update_image(self):
    if self.dataset is not None:
      assert isinstance(self.dataset, TFData)
      cursor = self.dataset.cursor
      image = np.squeeze(self.dataset.features[cursor])

      # Convert image data type
      if np.max(image) <= 1.0:
        image = np.int8(np.around(image * 255))

      # Adjust canvas size
      shape = image.shape
      width = max(shape[1], self.MIN_WIDTH)
      height = int(np.round(1.0 * width / shape[1] * shape[0]))
      self.canvas.config(width=width, height=height)
      self.image_height = height
      self.image_width = width
      # Draw image
      image = Image_.fromarray(image)
      image = image.resize((width, height))
      self.photo = ImageTk.PhotoImage(image=image)

      self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
    else:
      self.canvas.config(bg='light grey')

  def update_details(self):
    self.details.config(text='No details', fg='grey')

  def resize(self):
    self.form.geometry('{}x{}'.format(self.width, self.height))

  def save_dataset(self, _):
    if self.dataset is None:
      # console.show_status('No data set found')
      return
    filename = filedialog.asksaveasfilename(
      initialdir=self.lastdir, title='Save data set',
      filetypes=(("TFData files", '*.tfd'),))
    if filename == '':
      return
    if filename[-4:] != '.tfd':
      filename = '{}.tfd'.format(filename)

    self.dataset.save(filename)
    # Print status
    self.filename = filename
    print(">> Data set saved to '{}'".format(filename))
    self.update_title()

  def load_dataset(self, _):
    filename = filedialog.askopenfilename(
      initialdir=self.lastdir, title='Load data set',
      filetypes=(("TFData files", '*.tfd'),))
    if filename == '':
      return

    self.filename = filename
    self.set_data(TFData.load(filename))
    self.update_title()

    # Print status
    print(">> Loaded data set '{}'".format(filename))

  # endregion : Private Methods

  '''For some reasons, do not remove this line'''


if __name__ == '__main__':
  # mnist = load_mnist(r'..\..\data\MNIST', one_hot=True, validation_size=5000)
  # dataset = mnist[pedia.validation]
  dataset = r'C:\Users\HPEC\Documents\mnist_val_5000.tfd'
  # dataset = None
  viewer = ImageViewer(dataset)
  viewer.show()
