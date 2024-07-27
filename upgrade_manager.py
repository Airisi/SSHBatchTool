import asyncio
import os


class UpgradeManager:
    def __init__(self, ssh_manager):
        self.ssh_manager = ssh_manager

    async def execute_upgrade_async(self, file_path, script_path):
        if not await self.ssh_manager.ping_host():
            raise Exception(f'Host {self.ssh_manager.host} is not reachable.')

        remote_file_path = f'/tmp/{os.path.basename(file_path)}'
        remote_script_path = f'/tmp/{os.path.basename(script_path)}'

        try:
            await self.ssh_manager.connect_async()
            await self.report_progress(10)

            # 上传文件和脚本
            await self.ssh_manager.upload_file_async(file_path, remote_file_path)
            await self.report_progress(30)
            await self.ssh_manager.upload_file_async(script_path, remote_script_path)
            await self.report_progress(50)

            # 给脚本执行权限
            await self.ssh_manager.execute_command_async(f'chmod +x {remote_script_path}')
            await self.report_progress(70)

            # 执行升级脚本
            stdout, stderr = await self.ssh_manager.execute_command_async(f'{remote_script_path} {remote_file_path}')
            await self.report_progress(90)

            if stderr:
                raise Exception(stderr)

            await self.report_progress(100)
            return stdout or "Successfully upgraded."

        except Exception as e:
            raise Exception(str(e))

        finally:
            await self.ssh_manager.execute_command_async(f'rm -f {remote_file_path} {remote_script_path}')
            await self.ssh_manager.close_async()

    @staticmethod
    async def report_progress(progress):
        """
        向主线程报告升级进度
        """
        loop = asyncio.get_event_loop()
        if hasattr(loop, 'report_progress'):
            loop.report_progress(progress)
        await asyncio.sleep(0.1)
