import argparse
import functools
import json
import os
import uuid
from datetime import datetime
from queue import Queue
from threading import Thread
from typing import TextIO

import jwt
import requests


class PublishingProcessor:
    host: str
    username: str
    password: str

    action: str
    filename: str
    execution_context: dict

    access_token: str
    api_key: str

    package_version: dict
    log: TextIO

    def __init__(self):
        with open('config.json', 'r', encoding='utf-8') as f:
            self.__dict__.update(json.loads(f.read(), encoding='utf-8'))
        for folder in ['files', 'keys', 'logs', 'packages']:
            if not os.path.exists(folder):
                os.mkdir(folder)

    def request_and_check(self, method, *args, **kwargs) -> requests.Response:
        start_time = datetime.now()
        response = getattr(requests, method)(*args, **kwargs)
        print(f'Request [{method.upper()}] {args[0] if len(args) > 0 else kwargs["url"]} finished in '
              f'{(datetime.now() - start_time).total_seconds():.2f}s with status code {response.status_code}.')
        if response.status_code not in (200, 204):
            if hasattr(self, 'log'):
                self.log.write(f'\t[{datetime.now().isoformat()}] '
                               f'Request [{method.upper()}] {args[0] if len(args) > 0 else kwargs["url"]} '
                               f'failed with status code {response.status_code}.\n'
                               f'\tResponse: {json.dumps(response.json(), ensure_ascii=False)}\n')
            print(json.dumps(response.json(), indent=4, ensure_ascii=False))
            raise AssertionError
        return response

    def post(self, *args, **kwargs):
        return self.request_and_check('post', *args, **kwargs)

    def get(self, *args, **kwargs):
        return self.request_and_check('get', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.request_and_check('put', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request_and_check('delete', *args, **kwargs)

    def auth(self):
        # Login
        token = self.post(
            url=f'{self.host}/api/login',
            json={
                'username': self.username,
                'password': self.password
            }
        ).json()
        user_id = token['userId']
        self.access_token = token["accessToken"]
        print(f'Successfully login with user {user_id}, pubisher {token["publisherId"]}.')

        # Check private key
        key_file = f'keys/{user_id}.json'
        if not os.path.exists(key_file):
            key = self.post(
                url=f'{self.host}/api/publishing-key',
                headers=self.auth_headers
            ).json()
            with open(key_file, 'w') as f:
                f.write(json.dumps(key, indent=4))
            print(f'Successfully generated key and stored in {key_file}.')

        # Generate api key
        with open(key_file, 'r') as f:
            key = json.loads(f.read())
            private_key = f'-----BEGIN PRIVATE KEY-----\n{key["privateKey"]}\n-----END PRIVATE KEY-----'
            payload = {
                'sub': str(key['keyChainId']),
                'iss': str(key['keyChainId']),
                'iat': datetime.now().timestamp() - 60,
                'exp': datetime.now().timestamp() + 86400,  # expire in 1 day
                'aud': 'genesis',
                'scope': 'genesis.generateAccessToken'
            }
            self.api_key = jwt.encode(
                payload=payload,
                key=private_key,
                algorithm='RS256',
                headers={'kid': str(key['id']), 'uid': str(user_id)}
            )
        print('Successfully encoded API key.')

    @property
    def auth_headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}'
        }

    @property
    def publishing_headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}'
        }

    def execute(self, options):
        self.action = options.action.lower()
        if self.action not in {'save', 'saveall', 'submit', 'package', 'version', 'delete', 'deprecate', 'launch',
                               'categories', 'unity', 'limit'}:
            raise AttributeError('Invalid argument "--action".')
        if self.action in {'save', 'submit'}:
            if options.name is None:
                raise AttributeError('Missing argument "--name".')
            self.filename = f'packages/{options.name}.json'
            with open(self.filename, 'r', encoding='utf-8') as f:
                self.execution_context = json.loads(f.read(), encoding='utf-8')
        elif self.action in {'version', 'delete'}:
            if options.version is None:
                raise AttributeError('Missing argument "--version".')
        elif self.action in {'package', 'deprecate'}:
            if options.package is None:
                raise AttributeError('Missing argument "--package".')

        if self.action == 'save':
            if self.execution_context.get('packageId') is None:
                self.create()
            self.save()
            if self.execution_context.get('submission') is not None:
                self.submit()
        if self.action == 'saveall':
            log = f'logs/{datetime.now().isoformat().rsplit(".", 1)[0].replace(":", "")}.log'
            with open(log, 'w'):
                pass
            filenames = [filename for filename in os.listdir('packages') if filename.endswith('.json')]
            for filename in filenames:
                self.filename = f'packages/{filename}'
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.execution_context = json.loads(f.read(), encoding='utf-8')
                with open(log, 'a') as self.log:
                    self.log.write(f'{filename.rsplit(".", 1)[0]}')
                    try:
                        if self.execution_context.get('packageId') is None:
                            self.create()
                        self.log.write(f' ({self.execution_context["packageId"]}):\n')
                        self.save()
                        self.log.write(f'\t[{datetime.now().isoformat()}] Successfully saved.\n')
                        if self.execution_context.get('submission') is not None:
                            self.submit()
                            self.log.write(f'\t[{datetime.now().isoformat()}] Successfully submitted.\n')
                    except:
                        pass
        elif self.action == 'submit':
            self.get_draft_version(self.execution_context['packageId'])
            self.submit()
        elif self.action == 'package':
            self.get_package(options.package)
        elif self.action == 'version':
            self.get_package_version(options.version)
        elif self.action == 'delete':
            self.delete_draft_version(options.version)
        elif self.action == 'deprecate':
            self.deprecate_package(options.package)
        elif self.action == 'launch':
            self.setup_launch_discount(options.packages, options.discount, options.duration)
        elif self.action == 'categories':
            self.list_categories()
        elif self.action == 'unity':
            self.list_unity_versions()
        elif self.action == 'limit':
            self.show_limit()

    def create(self):
        package = self.post(
            url=f'{self.host}/store-publishing/package',
            json={
                'name': self.execution_context['metadatas']['en_US']['name'],
                'category': self.execution_context['category']
            },
            headers=self.publishing_headers
        ).json()
        print(f'Successfully created package {package["id"]} with draft version {package["versions"][0]["id"]}.')
        self.execution_context['packageId'] = package['id']
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(json.dumps(self.execution_context, indent=4, ensure_ascii=False))

    def save(self):
        self.get_draft_version(self.execution_context['packageId'])
        # Upload artworks
        for artwork in self.execution_context.get('artworks', []):
            if artwork['type'] in {'screenshot', 'audio', 'video'}:
                self.package_version = self.post(
                    url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}'
                        f'/{artwork["type"]}',
                    files={'file': open(artwork["source"], 'rb')},
                    headers=self.publishing_headers
                ).json()
            else:
                self.package_version = self.post(
                    url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}'
                        f'/media/{artwork["type"]}',
                    data={'url': artwork['source']},
                    headers=self.publishing_headers
                ).json()
            print(f'Successfully uploaded artwork {artwork["type"]} from {artwork["source"]}.')
        # Upload key images
        for key_image_type, source in self.execution_context.get('keyImages', dict()).items():
            if source is not None:
                self.package_version = self.post(
                    url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}'
                        f'/keyimage/{key_image_type.replace("_", "-")}',
                    files={'file': open(source, 'rb')},
                    headers=self.publishing_headers
                ).json()
                print(f'Successfully uploaded key image {key_image_type} from {source}.')
        # Upload unitypackages
        for unity_version, unitypackage in self.execution_context.get('unitypackages', dict()).items():
            if unitypackage is not None and unitypackage.get('source') is not None \
                    and (unitypackage.get('alwaysUpload') is True or str(os.path.getsize(unitypackage['source'])) !=
                         self.package_version.get('unitypackages', dict()).get(unity_version, dict()).get('size')):
                self.upload_unitypackage(unity_version, unitypackage['source'],
                                         unitypackage.get('slices'), unitypackage.get('threads'))
        # Update package version
        self.package_version = self.put(
            url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}',
            json={
                'versionName': self.execution_context.get('versionName'),
                'price': self.execution_context.get('price'),
                'category': self.execution_context.get('category'),
                'metadatas': {locale: self.execution_context.get('metadatas', dict()).get(locale)
                              for locale in ['en_US', 'zh_CN', 'ko_KR', 'ja_JP']},
                'tags': [tag.strip() for tag in self.execution_context.get('tags').split(',')]
                if isinstance(self.execution_context.get('tags'), str) else self.execution_context.get('tags'),
                'artworks': self.package_version['artworks']
                [len(self.package_version['artworks']) - len(self.execution_context.get('artworks', [])):],
                'keyImages': {
                    key_image_type: None
                    for key_image_type in ['icon', 'card', 'cover', 'social_media']
                    if self.execution_context.get('keyImages', dict()).get(key_image_type) is None
                },
                'unitypackages': {
                    **{
                        unity_version: None
                        for unity_version in self.package_version.get('unitypackages', dict()).keys()
                    },
                    **{
                        unity_version: {
                            'srps': unitypackage.get('srps', []),
                            'dependencies': unitypackage.get('dependencies', [])
                        }
                        for unity_version, unitypackage in self.execution_context.get('unitypackages', dict()).items()
                        if unitypackage is not None
                    }
                }
            },
            headers=self.publishing_headers
        ).json()
        print(f'Successfully updated package version data.')

    def submit(self):
        self.post(
            url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}/submit',
            json={
                'submitMessage': self.execution_context['submission'].get('submitMessage'),
                'autoPublish': self.execution_context['submission'].get('autoPublish'),
                'acceptLatestTerms': self.execution_context['submission'].get('acceptLatestTerms')
            },
            headers=self.publishing_headers
        )
        self.package_version = self.get(
            url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}',
            headers=self.publishing_headers
        ).json()
        assert self.package_version['status'] == 'submitted'
        print(f'Successfully submitted package version.')

    def get_draft_version(self, package_id):
        package = self.get(
            url=f'{self.host}/store-publishing/package/{package_id}',
            headers=self.publishing_headers
        ).json()
        if all(package_version['status'] != 'draft' for package_version in package['versions']):
            # Create draft version
            self.package_version = self.post(
                url=f'{self.host}/store-publishing/package-version',
                json={
                    'packageId': self.execution_context['packageId']
                },
                headers=self.publishing_headers
            ).json()
            print(f'Successfully created draft version {self.package_version["id"]} of '
                  f'package {self.execution_context["packageId"]}.')
        else:
            # Get draft version
            for package_version in package['versions']:
                if package_version['status'] == 'draft':
                    self.package_version = self.get(
                        url=f'{self.host}/store-publishing/package-version/{package_version["id"]}',
                        headers=self.publishing_headers
                    ).json()
                    print(f'Successfully get draft version {self.package_version["id"]} of '
                          f'package {self.execution_context["packageId"]}.')
                    return

    def upload_unitypackage(self, unity_version, source, slices=None, thread_nums=1):
        size = os.path.getsize(source)
        if slices is None:
            slices = (size - 1) // (500 * 1024 * 1024) + 1
        sizes = [size // slices] * (slices - 1) + [size // slices + size % slices]
        # Prepare for upload
        self.post(
            url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}'
                f'/unitypackage/prepare',
            json={
                'unityVersion': unity_version,
                'sizes': sizes
            },
            headers=self.publishing_headers
        )
        print(f'Successfully prepared to upload unitypackage in {slices} slices.')
        tasks = Queue()
        failures, context = [], {'index': 0}
        f = open(source, 'rb')
        for slice_size in sizes:
            tasks.put(
                functools.partial(self.upload_unitypackage_slice, f, slice_size, unity_version, failures, context)
            )
        threads = [Thread(target=self.upload_unitypackage_thread, args=(tasks,))
                   for _ in range(thread_nums)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if len(failures) > 0:
            raise failures[0]

    @staticmethod
    def upload_unitypackage_thread(tasks: Queue):
        while not tasks.empty():
            tasks.get()()

    def upload_unitypackage_slice(self, f, size, unity_version, failures, context):
        tempfile = f'{uuid.uuid4()}.partial'
        index = context['index']
        context['index'] += 1
        with open(tempfile, 'wb') as g:
            g.write(f.read(size))
        try:
            self.post(
                url=f'{self.host}/store-publishing/package-version/{self.package_version["id"]}/unitypackage',
                files={'file': open(tempfile, 'rb')},
                data={'unityVersion': unity_version, 'index': index},
                headers=self.publishing_headers
            )
            print(f'Successfully uploaded slice {index} with {size / 1024:.2f} KB.')
        except Exception as e:
            failures.append(e)
        finally:
            os.remove(tempfile)

    def get_package(self, package_id):
        print(json.dumps(self.get(
            url=f'{self.host}/store-publishing/package/{package_id}',
            headers=self.publishing_headers
        ).json(), indent=4, ensure_ascii=False))

    def get_package_version(self, package_version_id):
        print(json.dumps(self.get(
            url=f'{self.host}/store-publishing/package-version/{package_version_id}',
            headers=self.publishing_headers
        ).json(), indent=4, ensure_ascii=False))

    def delete_draft_version(self, package_version_id):
        self.delete(
            url=f'{self.host}/store-publishing/package-version/{package_version_id}',
            headers=self.publishing_headers
        )
        print(f'Successfully deleted draft version {package_version_id}.')

    def deprecate_package(self, package_id):
        self.delete(
            url=f'{self.host}/store-publishing/package/{package_id}/deprecate',
            headers=self.publishing_headers
        )
        print(f'Successfully deprecated package {package_id}.')

    def setup_launch_discount(self, package_ids, discount, duration):
        package_ids = [int(package_id.strip()) for package_id in package_ids.split(',')]
        self.post(
            url=f'{self.host}/store-publishing/promotion/launch',
            json={
                'packageIds': package_ids,
                'discount': discount,
                'duration': duration
            },
            headers=self.publishing_headers
        )
        print(f'Successfully setup launch discount for {len(package_ids)} packages: {package_ids}.')

    def list_categories(self):
        categories = self.get(
            url=f'{self.host}/store-publishing/fetch/categories',
            headers=self.publishing_headers
        ).json()
        print(json.dumps(categories, indent=4))

    def list_unity_versions(self):
        unity_versions = self.get(
            url=f'{self.host}/store-publishing/fetch/unity-versions',
            headers=self.publishing_headers
        ).json()
        print(json.dumps(unity_versions, indent=4))

    def show_limit(self):
        limit = self.get(
            url=f'{self.host}/api/publishing-limit',
            headers=self.auth_headers
        ).json()
        print(json.dumps(limit, indent=4))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', required=True, type=str, dest='action',
                        help='Save: create/update/submit package, should give "--name".\n'
                             'SaveAll: create/update/submit packages in "package" folder and generate a log.\n'
                             'Submit: submit package, should give "--name".\n'
                             'Package: get package, should give "--package".\n'
                             'Version: get package version, should give "--version".\n'
                             'Delete: delete draft package version, should give "--version".\n'
                             'Deprecate: deprecate published version, should give "--package".\n'
                             'Launch: set launch discount for packages, should give "--packages", "--discount",'
                             ' "--duration"\n'
                             'Categories: list all categories.\n'
                             'Unity: list all unity versions.\n'
                             'Limit: show OpenAPI limit of publisher account.')
    parser.add_argument('--name', type=str, dest='name', help='Argument for action "Save/Submit".')
    parser.add_argument('--version', type=str, dest='version', help='Argument for action "Delete".')
    parser.add_argument('--package', type=str, dest='package', help='Argument for action "Deprecate".')
    parser.add_argument('--packages', type=str, dest='packages', help='Argument for action "Launch".')
    parser.add_argument('--discount', type=int, dest='discount', help='Argument for action "Launch".')
    parser.add_argument('--duration', type=int, dest='duration', help='Argument for action "Launch".')
    options = parser.parse_args()

    processor = PublishingProcessor()
    processor.auth()
    processor.execute(options)
