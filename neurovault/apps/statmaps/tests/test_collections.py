from django.test import TestCase, Client, override_settings, RequestFactory
from django.core.urlresolvers import reverse
from neurovault.apps.statmaps.models import Collection,User, Atlas
from django.core.files.uploadedfile import SimpleUploadedFile
from uuid import uuid4
import tempfile
import os
import shutil
from neurovault.apps.statmaps.utils import detect_afni4D, split_afni4D_to_3D
import nibabel
from .utils import clearDB
from neurovault.settings import PRIVATE_MEDIA_ROOT

from neurovault.apps.statmaps.views import delete_collection



class CollectionSharingTest(TestCase):

    def setUp(self):
        self.user = {}
        self.client = {}
        for role in ['owner','contrib','someguy']:
            self.user[role] = User.objects.create_user('%s_%s' % (role,
                                                       self.uniqid()), None,'pwd')
            self.user[role].save()
            self.client[role] = Client()
            self.client[role].login(username=self.user[role].username,
                                    password='pwd')

        self.coll = Collection(
            owner=self.user['owner'],
            name="Test %s" % self.uniqid()
        )
        self.coll.save()
        self.coll.contributors.add(self.user['contrib'])

    def uniqid(self):
        return str(uuid4())[:8]

    @override_settings(CRISPY_FAIL_SILENTLY=False)
    def testCollectionSharing(self):

        #view_url = self.coll.get_absolute_url()
        edit_url = reverse('edit_collection',kwargs={'cid': self.coll.pk})
        resp = {}

        for role in ['owner','contrib','someguy']:
            resp[role] = self.client[role].get(edit_url, follow=True)

        """
        assert that owner and contributor can edit the collection,
        and that some guy cannot:
        """
        self.assertEqual(resp['owner'].status_code,200)
        self.assertEqual(resp['contrib'].status_code,200)
        self.assertEqual(resp['someguy'].status_code,403)

        """
        assert that only the owner can view/edit contributors:
        """
        self.assertTrue('contributor' in resp['owner'].content.lower())
        self.assertFalse('contributor' in resp['contrib'].content.lower())


class DeleteCollectionsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.test_path = os.path.abspath(os.path.dirname(__file__))
        self.user = User.objects.create(username='neurovault')
        self.client = Client()
        self.client.login(username=self.user)
        self.Collection1 = Collection(name='Collection1',owner=self.user)
        self.Collection1.save()
        self.unorderedAtlas = Atlas(name='unorderedAtlas', description='',collection=self.Collection1)
        self.unorderedAtlas.file = SimpleUploadedFile('VentralFrontal_thr75_summaryimage_2mm.nii.gz', file(os.path.join(self.test_path,'test_data/api/VentralFrontal_thr75_summaryimage_2mm.nii.gz')).read())
        self.unorderedAtlas.label_description_file = SimpleUploadedFile('test_VentralFrontal_thr75_summaryimage_2mm.xml', file(os.path.join(self.test_path,'test_data/api/unordered_VentralFrontal_thr75_summaryimage_2mm.xml')).read())
        self.unorderedAtlas.save()
        
        self.Collection2 = Collection(name='Collection2',owner=self.user)
        self.Collection2.save()
        self.orderedAtlas = Atlas(name='orderedAtlas', collection=self.Collection2, label_description_file='VentralFrontal_thr75_summaryimage_2mm.xml')
        self.orderedAtlas.file = SimpleUploadedFile('VentralFrontal_thr75_summaryimage_2mm.nii.gz', file(os.path.join(self.test_path,'test_data/api/VentralFrontal_thr75_summaryimage_2mm.nii.gz')).read())
        self.orderedAtlas.label_description_file = SimpleUploadedFile('test_VentralFrontal_thr75_summaryimage_2mm.xml', file(os.path.join(self.test_path,'test_data/api/VentralFrontal_thr75_summaryimage_2mm.xml')).read())
        self.orderedAtlas.save()
    
    def tearDown(self):
        clearDB()
        
    def testDeleteCollection(self):
        self.client.login(username=self.user)
        pk1 = self.Collection1.pk
        pk2 = self.Collection2.pk
        request = self.factory.get('/collections/%s/delete' %pk1)
        request.user = self.user
        delete_collection(request, str(pk1))
        imageDir = os.path.join(PRIVATE_MEDIA_ROOT, 'images')
        dirList = os.listdir(imageDir)
        print dirList
        self.assertIn(str(self.Collection2.pk), dirList)
        self.assertNotIn(str(self.Collection1.pk), dirList)
    


class Afni4DTest(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        app_path = os.path.abspath(os.path.dirname(__file__))
        self.afni_file = os.path.join(app_path,'test_data/TTatlas.nii.gz')
        self.nii_file = os.path.abspath(os.path.join(app_path,'../static/anatomical/MNI152.nii.gz'))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        clearDB()

    """
    TTatlas is the example 4D file that ships with afni, has two sub-bricks:

    vagrant@localhost$ 3dinfo  TTatlas.nii.gz
    ++ 3dinfo: AFNI version=AFNI_2011_12_21_1014 (Nov 22 2014) [64-bit]
    <<... snip ..>>
    Number of values stored at each pixel = 2
      -- At sub-brick #0 'uu3[0]' datum type is byte:            0 to 77
         keywords = uu3+tlrc[0] ; TTatlas+tlrc[0] ; uu3+tlrc[0]
      -- At sub-brick #1 'uu5[0]' datum type is byte:            0 to 151
         keywords = uu5+tlrc[0] ; TTatlas+tlrc[1] ; uu5+tlrc[0]
    """

    def testAfni4DSlicing(self):
        test_afni = detect_afni4D(nibabel.load(self.afni_file))
        test_non_afni = detect_afni4D(nibabel.load(self.nii_file))

        bricks = split_afni4D_to_3D(nibabel.load(self.afni_file),tmp_dir=self.tmpdir)

        # check detection of 4D is correct
        self.assertTrue(test_afni)
        self.assertFalse(test_non_afni)

        # check for 2 sub bricks
        self.assertEquals(len(bricks),2)

        # check that brick labels match afni 3dinfo binary output
        self.assertEquals(bricks[0][0],'uu3[0]')
        self.assertEquals(bricks[1][0],'uu5[0]')

        # check that sliced niftis exist at output location
        self.assertTrue(os.path.exists(bricks[0][1]))
        self.assertTrue(os.path.exists(bricks[1][1]))
