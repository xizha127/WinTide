#!/usr/bin/env python3
"""Create a private FAT boot image by copying Microsoft EFI files, never a raw host disk."""
import argparse,os,pathlib,shutil,subprocess,tempfile

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,help='Mounted EFI filesystem root, e.g. /boot');p.add_argument('--output',required=True);a=p.parse_args()
 if os.geteuid()!=0:p.error('Run with sudo for the temporary loop mount')
 source=pathlib.Path(a.source).resolve();out=pathlib.Path(a.output).absolute()
 boot=source/'EFI/Microsoft/Boot'
 if not (boot/'BCD').is_file() or not (boot/'bootmgfw.efi').is_file():p.error('Microsoft EFI boot files not found at source')
 if str(out).startswith('/dev/') or out.exists() or out.is_symlink():p.error('Output must be a NEW regular image file outside /dev')
 if not out.parent.is_dir():p.error('Create the output parent directory first')
 with out.open('xb') as f:f.truncate(512*1024*1024)
 out.chmod(0o600)
 subprocess.run(['mkfs.vfat','-F','32','-n','VM_EFI',str(out)],check=True)
 with tempfile.TemporaryDirectory(prefix='winapps-private-efi-') as tmp:
  subprocess.run(['mount','-o','loop',str(out),tmp],check=True)
  try:
   dest=pathlib.Path(tmp);shutil.copytree(source/'EFI/Microsoft',dest/'EFI/Microsoft',copy_function=shutil.copyfile)
   (dest/'EFI/Boot').mkdir(parents=True,exist_ok=True);shutil.copyfile(boot/'bootmgfw.efi',dest/'EFI/Boot/bootx64.efi')
   os.sync()
  finally:subprocess.run(['umount',tmp],check=True)
 print('Private EFI image created:',out)
 print('If BCD references fail, repair only this private image using BCDBoot in Windows recovery. See docs/physical-disk.md.')
if __name__=='__main__':main()
