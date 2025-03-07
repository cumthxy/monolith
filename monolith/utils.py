# Copyright 2022 ByteDance and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import tensorflow as tf


def find_main():
  """Find base directory of our codebase, which should be current dir
  for all binaries in monolith codebase."""
  path = os.path.abspath(__file__)

  splits = ['/__main__/', '/site-packages/', '/monolith/']
  main_dir = None
  for split in splits:
    if split in path:
      end = path.rfind(split)
      if split == '/monolith/':
        main_dir = path[0:end]
      else:
        main_dir = os.path.join(path[0:end], split.strip('/'))
      break

  if main_dir is not None and os.path.exists(
      os.path.join(main_dir, 'monolith')):
    return main_dir
  else:
    raise ValueError(
        "Unable to find the monolith base directory. This file directory is {}. Are you running under bazel structure?"
        .format(path))


def get_libops_path(lib_name):
  base = find_main()  # monolith base
  return os.path.join(base, lib_name)


def enable_monkey_patch():
  name = "tensorflow.python.training.monitored_session"
  orig_mod = sys.modules.get(name)
  if orig_mod is None:
    orig_mod = __import__(name)
  setattr(orig_mod, "_PREEMPTION_ERRORS", (tf.errors.AbortedError,))


def CopyFile(src, dst, overwrite=True, skip_nonexist=True, max_retries=5):
  for _ in range(max_retries):
    try:
      tf.io.gfile.copy(src, dst, overwrite=overwrite)
    except tf.errors.NotFoundError as e:
      if skip_nonexist:
        continue
      else:
        raise e
    break


def CopyRecursively(src: str,
                    dst: str,
                    max_workers: int = 1,
                    skip_nonexist: bool = True,
                    max_retries: int = 5):
  src_dst = []

  def _CopyRecursivelyImpl(src, dst):
    if not tf.io.gfile.exists(src):
      if skip_nonexist:
        return
      raise ValueError("{} doesn't exist!".format(src))
    if not tf.io.gfile.isdir(src):
      if max_workers > 1:
        src_dst.append((src, dst))
      else:
        CopyFile(src, dst, overwrite=True, skip_nonexist=skip_nonexist)
      return
    if tf.io.gfile.exists(dst):
      tf.io.gfile.rmtree(dst)
    tf.io.gfile.makedirs(dst)
    for relpath in tf.io.gfile.listdir(src):
      src_path = os.path.join(src, relpath)
      dst_path = os.path.join(dst, relpath)
      _CopyRecursivelyImpl(src_path, dst_path)

  _CopyRecursivelyImpl(src, dst)
  if max_workers > 1:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
      executor.map(
          lambda args: CopyFile(
              args[0],
              args[1],
              overwrite=True,
              skip_nonexist=skip_nonexist,
              max_retries=max_retries), src_dst)
