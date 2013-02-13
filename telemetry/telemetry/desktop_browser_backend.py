# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
import os as os
import subprocess as subprocess
import shutil
import tempfile

from telemetry import browser_backend
from telemetry import util

class DesktopBrowserBackend(browser_backend.BrowserBackend):
  """The backend for controlling a locally-executed browser instance, on Linux,
  Mac or Windows.
  """
  def __init__(self, options, executable, is_content_shell):
    super(DesktopBrowserBackend, self).__init__(
        is_content_shell=is_content_shell,
        supports_extensions=not is_content_shell, options=options)

    # Initialize fields so that an explosion during init doesn't break in Close.
    self._proc = None
    self._tmpdir = None
    self._tmp_output_file = None

    self._executable = executable
    if not self._executable:
      raise Exception('Cannot create browser, no executable found!')

    if len(options.extensions_to_load) > 0 and is_content_shell:
      raise browser_backend.ExtensionsNotSupportedException(
          'Content shell does not support extensions.')

    self._port = util.GetAvailableLocalPort()

    args = [self._executable]
    args.extend(self.GetBrowserStartupArgs())
    if not options.show_stdout:
      self._tmp_output_file = tempfile.NamedTemporaryFile('w', 0)
      self._proc = subprocess.Popen(
          args, stdout=self._tmp_output_file, stderr=subprocess.STDOUT)
    else:
      self._proc = subprocess.Popen(args)

    try:
      self._WaitForBrowserToComeUp()
      self._PostBrowserStartupInitialization()
    except:
      self.Close()
      raise

  def GetBrowserStartupArgs(self):
    args = super(DesktopBrowserBackend, self).GetBrowserStartupArgs()
    args.append('--remote-debugging-port=%i' % self._port)
    args.append('--window-size=1280,1024')
    args.append('--enable-benchmarking')
    if not self.options.dont_override_profile:
      self._tmpdir = tempfile.mkdtemp()
      args.append('--user-data-dir=%s' % self._tmpdir)
    return args

  def IsBrowserRunning(self):
    return self._proc.poll() == None

  def GetStandardOutput(self):
    assert self._tmp_output_file, "Can't get standard output with show_stdout"
    self._tmp_output_file.flush()
    try:
      with open(self._tmp_output_file.name) as f:
        return f.read()
    except IOError:
      return ''

  def __del__(self):
    self.Close()

  def Close(self):
    super(DesktopBrowserBackend, self).Close()

    if self._proc:

      def IsClosed():
        if not self._proc:
          return True
        return self._proc.poll() != None

      # Try to politely shutdown, first.
      self._proc.terminate()
      try:
        util.WaitFor(IsClosed, timeout=1)
        self._proc = None
      except util.TimeoutException:
        pass

      # Kill it.
      if not IsClosed():
        self._proc.kill()
        try:
          util.WaitFor(IsClosed, timeout=5)
          self._proc = None
        except util.TimeoutException:
          self._proc = None
          raise Exception('Could not shutdown the browser.')

    if self._tmpdir and os.path.exists(self._tmpdir):
      shutil.rmtree(self._tmpdir, ignore_errors=True)
      self._tmpdir = None

    if self._tmp_output_file:
      self._tmp_output_file.close()
      self._tmp_output_file = None

  def CreateForwarder(self, *port_pairs):
    return DoNothingForwarder(*port_pairs)

class DoNothingForwarder(object):
  def __init__(self, *port_pairs):
    self._host_port = port_pairs[0].local_port

  @property
  def url(self):
    assert self._host_port
    return 'http://localhost:%i' % self._host_port

  def Close(self):
    self._host_port = None
