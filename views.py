"""REST API views."""
from django.views.generic.base import View
from django.db.models.fields import FieldDoesNotExist
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, \
        HttpResponseForbidden, HttpResponseBadRequest, Http404
import json

class RESTView(View):
    """Base view for RESTful API's on Django models."""

    @classmethod
    def urls(cls):
        """Returns the list of url patterns used by this API.

        These url patterns are:

        GET /
            Return the collection of entities

        GET /<entity>
            Return the details of ```<entity>```

        GET /<entity>/<link>/
            Return the collection of entities that are linked
            to ```<entity>``` by ```<link>```. By default ```<link>``` must
            be a many2many field in the Django model of ```<entity>```.

        GET /<entity>/<link>/<linked_entity>
            Return the entity ```<linked_entity>``` that is
            linked to ```<entity>``` by ```<link>```.

        PUT /<entity>
            Alter the properties of ```<entity>``` based on the key-value pairs
            in the payload. Return a HTTP 404 when ```<entity>``` cannot be
            found.

        DELETE /<entity>
            Delete the entity ```<entity>```.

        DELETE /<entity/<link>/<linked_entity>
            Remove the link between ```<entity>``` and ```<linked_entity>```
            that was identified by ```<link>```.
            By default ```<linked_entity>``` is not deleted.

        POST /
            Create a new entity based on the payload.
            Return a HTTP 302 redirect to the URL that returns the details
            of the newly created entity.

        POST /<method>
            Return the output of ```<method>```, where ```<method>``` is either
            a class method or a static method. The method must belong to the
            model class as returned by ```self.get_model(request)```.

        POST /<entity>/<link>/
            Add a new link between ```<entity>``` and the entity specified
            by a set of key-value pairs in the payload. By default a HTTP 404
            is returned if the specified entity cannot be found.

        POST /<entity>/<method>
            Return the output of ```<method>```, where ```<method>``` is an
            instance method. The method must belong to the instance referenced
            by ```<entity>```.

        POST /<entity>/<link>/<method>
            Return the output of ```<method>```, where ```<method>``` is either
            a class method or a static method. The method must belong to the
            model class that handles the ```<link>``` relation. By default
            this is the intermediate model in django that stores the many2many
            relationship.

        POST /<entity>/<link>/<linked_entity>/<method>
            Return the output of ```<method>```, where ```<method>``` is an
            instance method. The method must belong to the instance referenced
            by ```<linked_entity>```.
            The arguments of the method are the request object,
            the entity ```<entity>``` and the link name ```<link>```.
        """
        from django.conf.urls import url
        return [
            url(r'^/?$',
                cls.as_view(), name='collection'),
            url(r'^/([^/]+)/?$',
                cls.as_view(), name='entity'),
            url(r'^/([^/]+)/?$',
                cls.as_view(), name='collection_method'),
            url(r'^/'+'([^/]+)/'*2+'?$',
                cls.as_view(), name='linked_collection'),
            url(r'^/'+'([^/]+)/'*3+'?$',
                cls.as_view(), name='linked_entity'),
            url(r'^/'+'([^/]+)/'*3+'?$',
                cls.as_view(), name='linked_collection_method'),
            url(r'^/'+'([^/]+)/'*4+'?$',
                cls.as_view(), name='linked_entity_method')
        ]

    def get_model(self, request):
        """Return the model class for this REST API."""
        raise NotImplementedError("You must implement the get_model method.")

    def get_linked_model(self, request, link):
        """Return the linked model class identified by name."""
        model = self.get_model(request)
        try:
            field, _m, _d, m2m = model._meta.get_field_by_name(link)
        except FieldDoesNotExist:
            raise TypeError('Field `%s.%s` does not exist.' % (
                model.__name__, link,))
        if not m2m:
            raise TypeError('Field `%s.%s` is not a m2m field.' % (
                model.__name__, link,))

        return field.rel.to

    def get_queryset(self, request):
        """Return the base queryset that can be filtered."""
        return self.get_model(request).objects

    def get_linked_queryset(self, request, entity, link):
        """Return the base linked queryset that can be filtered."""
        try:
            m2m = entity._meta.get_field_by_name(link)[3]
        except FieldDoesNotExist:
            raise TypeError('Field `%s.%s` does not exist.' % (
                entity.__class__.__name__, link,))
        if not m2m:
            raise TypeError('Field `%s.%s` is not a m2m field.' % (
                entity.__class__.__name__, link,))

        return getattr(entity, link)

    def filter_queryset(self, request, queryset):
        """Return a filtered queryset based on the request."""
        fieldnames = queryset.model._meta.get_all_field_names()
        for field, value in request.GET.iteritems():
            if field in fieldnames:
                queryset = self.apply_filter(request, queryset, field, value)
        return queryset

    def apply_filter(self, request, queryset, field, value):
        """Apply the GET filter to the queryset."""
        field_obj = queryset.model._meta.get_field(field)
        if field_obj.rel is None:
            return queryset.filter(**{field:value})
        else:
            reference = get_object_or_404(field_obj.rel.to, pk=value)
            return queryset.filter(**{field:reference})

    def can_get_entity(self, request, entity):
        """Return if ```entity``` may be retrieved."""
        return True

    def can_get_linked_entity(self, request, entity, link, linked_entity):
        """Return if ```linked_entity``` may be retrieved."""
        return True

    def can_create_entity(self, request, data):
        """Return if ```data``` may be used to create an entity."""
        return True

    def can_create_linked_entity(self, request, entity, link, linked_entity):
        """Return if ```linked_entity``` may be linked to entity."""
        return True

    def can_edit_entity(self, request, entity):
        """Return if ```entity``` may be edited."""
        return self.can_get_entity(request, entity)

    def can_delete_entity(self, request, entity):
        """Return if ```entity``` may be deleted."""
        return self.can_edit_entity(request, entity)

    def can_delete_linked_entity(self, request, entity, link, linked_entity):
        """Return if ```linked_entity``` may be deleted."""
        return self.can_create_linked_entity(request, entity, link, linked_entity)

    def get_collection(self, request):
        """Return a collection of entities."""
        base_queryset = self.get_model(request).objects
        queryset = self.filter_queryset(request, base_queryset)
        return filter(lambda entity: self.can_get_entity(request, entity),
                set(queryset.all()))

    def get_linked_collection(self, request, instance_pk_or_entity, link):
        """Return a collection of linked entities by linked name."""
        entity = self.get_entity(request, instance_pk_or_entity)
        base_queryset = self.get_linked_queryset(request, entity, link)
        queryset = self.filter_queryset(request, base_queryset)
        return filter(
                (lambda linked_entity: self.can_get_linked_entity(
                        request, entity, link, linked_entity)),
                set(queryset.all()))

    def get_entity(self, request, instance_pk_or_entity):
        """Return the entity identified by instance_pk."""
        if isinstance(instance_pk_or_entity, self.get_model(request)):
            entity = instance_pk_or_entity
        else:
            base_queryset = self.get_model(request).objects
            queryset = self.filter_queryset(request, base_queryset)
            try:
                entity = queryset.get(pk=instance_pk_or_entity)
            except queryset.model.DoesNotExist:
                raise TypeError('There is no %s instance with primary key: %s' % (
                    queryset.model.__name__, instance_pk))
            except ValueError:
                raise TypeError('Invalid primary key value for %s instance: %s' % (
                    queryset.model.__name__, instance_pk))

        if self.can_get_entity(request, entity):
            return entity
        else:
            return HttpResponseForbidden()

    def get_linked_entity(self, request, instance_pk_or_entity, link,
            linked_instance_pk):
        """Return the linked entity identified by linked_instance_pk."""
        entity = self.get_entity(request, instance_pk_or_entity)
        base_queryset = self.get_linked_queryset(request, entity, link)
        queryset = self.filter_queryset(request, base_queryset)
        try:
            linked_entity = queryset.get(pk=linked_instance_pk)
        except queryset.model.DoesNotExist:
            raise TypeError('There is no %s instance with primary key: %s' % (
                queryset.model.__name__, linked_instance_pk))
        except ValueError:
            raise TypeError('Invalid primary key value for %s instance: %s' % (
                queryset.model.__name__, linked_instance_pk))
        else:
            if self.can_get_linked_entity(request, entity, link,
                    linked_entity):
                return linked_entity
            else:
                return HttpResponseForbidden()

    def get_model_form_fields(self, request):
        """Return the list of available fields for the modelform."""
        model = self.get_model(request)
        return filter(lambda x: x.editable and not x.primary_key,
                model._meta.fields)


    def get_model_form(self, request, desired_fields=None):
        """Return a ModelForm subclass for this API's model or None."""
        from django.forms.models import modelform_factory
        model = self.get_model(request)
        fields = self.get_model_form_fields(request)

        if desired_fields is not None:
            fields = filter(lambda x: x.name in desired_fields, fields)

        if fields:
            field_names = map(lambda x: x.name, fields)
            return modelform_factory(model, fields=field_names)
        else:
            return None

    def create_entity(self, request, data):
        """Create an entity using ```data```."""
        if not isinstance(data, dict):
            raise ValueError('POST data should contain dictionary')

        if not self.can_create_entity(request, data):
            return HttpResponseForbidden()

        FormCls = self.get_model_form(request)
        if FormCls is None:
            return HttpResponseForbidden()
        form = FormCls(data)
        try:
            entity = form.save()
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        else:
            return entity

    def create_linked_entity(self, request, instance_pk_or_entity, link,
            data):
        """Add the entity ``linked_instance_pk``` to the linked collection."""
        entity = self.get_entity(request, instance_pk_or_entity)

        try:
            linked_model = self.get_linked_model(request, link)
            queryset = self.get_linked_queryset(request, entity,
                    link)
        except TypeError as e:
            raise e
        else:
            if not isinstance(data, dict):
                raise ValueError('POST data should contain dictionary')
            else:
                linked_entity = get_object_or_404(linked_model, **data)
                if not self.can_create_linked_entity(request, entity,
                        link, linked_entity):
                    return HttpResponseForbidden()

                queryset.add(linked_entity)
                entity.save()

    def edit_entity(self, request, instance_pk, data):
        """Create an entity using ```data```."""
        if not isinstance(data, dict):
            raise ValueError('PUT data should contain dictionary')

        entity = self.get_entity(request, instance_pk)

        if not self.can_edit_entity(request, entity):
            return HttpResponseForbidden()

        FormCls = self.get_model_form(request, data.keys())
        if FormCls is None:
            return HttpResponseForbidden()
        form = FormCls(data, instance=entity)

        try:
            entity = form.save()
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        else:
            return entity

    def delete_entity(self, request, instance_pk):
        """Delete an entity."""

        entity = self.get_entity(request, instance_pk)

        if not self.can_delete_entity(request, entity):
            return HttpResponseForbidden()

        entity.delete()

    def delete_linked_entity(self, request, instance_pk, link,
            linked_instance_pk):
        """Delete a linked entity."""

        entity = self.get_entity(request, instance_pk)
        linked_entity = self.get_linked_entity(request, entity,
                link, linked_instance_pk)

        if not self.can_delete_linked_entity(request, entity, link,
                linked_entity):
            return HttpResponseForbidden()

        queryset = self.get_linked_queryset(request, entity, link)
        queryset.remove(linked_entity)

    def call_collection_method(self, request, method, data):
        """Return the output of the collection method ```method```."""
        model = self.get_model(request)
        collection_method = getattr(model, method, None)
        if callable(collection_method):
            if type(collection_method) == type(lambda x: x):
                # Static method
                return collection_method(request, data)
            elif collection_method.im_self is not None:
                # Bound method
                return collection_method(request, data)
            else:
                # Unbound method
                raise TypeError('Unbound methods are not allowed.')
        else:
            raise TypeError('`%s.%s` is not a callable.' % (
                model.__name__, method,))

    def call_entity_method(self, request, entity, method, data):
        """Return the output of the entity method ```method```."""
        entity = self.get_entity(request, entity)
        entity_method = getattr(entity, method, None)
        if callable(entity_method):
            if type(entity_method) == type(lambda x: x):
                # Static method
                raise TypeError('Static methods are not allowed.')
            elif entity_method.im_self is not None:
                # Bound method
                return entity_method(request, data)
            else:
                # Unbound method
                raise TypeError('Unbound methods are not allowed.')
        else:
            raise TypeError('`%s.%s` is not a callable.' % (
                entity.__class__.__name__, method,))

    def call_linked_collection_method(self, request, entity, link,
            method, data):
        return HttpResponse("%s(%s)" % (method, str(data)))

    def call_linked_entity_method(self, request, entity, link,
            linked_entity, method, data):
        return HttpResponse("%s(%s)" % (method, str(data)))

    def serialize_for_json(self, request, response):
        """Return a JSON-serializable representation of the response."""
        # Test if response is already serializable. If so, keep it as is
        try:
            json.dumps(response)
        except TypeError as e:
            pass
        else:
            return response

        # If response is a dictionary, serialize its values
        if isinstance(response, dict):
            for key in response:
                response[key] = self.serialize_for_json(request, response[key])
            return response

        # Try serializing it as an iterable object
        try:
            it = iter(response)
        except TypeError:
            pass
        else:
            return [self.serialize_for_json(request, elem) for elem in it]

        # Try serializing it as an object with a describe function
        if callable(getattr(response, 'describe', None)):
            response = self.serialize_for_json(request, response.describe())

        # Test the serialization again, if it fails cast it to a string
        try:
            json.dumps(response)
        except TypeError as e:
            return str(response)
        else:
            return response

    def reply_to_response(self, request, reply):
        """Return a HttpResponse object containing the ```reply```."""
        if reply is None:
            return HttpResponse(status=204)
        elif isinstance(reply, HttpResponse):
            return reply
        else:
            serialized_reply = self.serialize_for_json(request, reply)
            return HttpResponse(json.dumps(serialized_reply),
                content_type='application/json')

    def get(self, request, *args):
        """Handle GET request."""
        cargs = len(args)

        try:
            if cargs == 0:
                # URL: /
                reply = self.get_collection(request)
            elif cargs == 1:
                # URL: /entity
                reply = self.get_entity(request, args[0])
            elif cargs == 2:
                # URL: /entity/collection/
                reply = self.get_linked_collection(request, args[0], args[1])
            elif cargs == 3:
                # URL: /entity/collection/entity
                reply = self.get_linked_entity(
                        request, args[0], args[1], args[2])
            else:
                raise Http404

            return self.reply_to_response(request, reply)

        except TypeError as e:
            if settings.DEBUG:
                raise Http404(str(e))
            else:
                raise Http404()

        except Exception as e:
            if settings.DEBUG:
                return HttpResponseBadRequest(str(e))
            else:
                return HttpResponseBadRequest()

    def post(self, request, *args):
        """Handle POST request."""
        cargs = len(args)

        try:
            data = json.loads(request.body)
            if cargs == 0:
                # URL: /
                reply = self.create_entity(request, data)
            elif cargs == 1:
                # URL: /method
                reply = self.call_collection_method(
                        request, args[0], data)
            elif cargs == 2:
                try:
                    # URL 1): /entity/collection/
                    reply = self.create_linked_entity(
                            request, args[0], args[1], data)
                except TypeError:
                    # URL 2): /entity/method/
                    reply = self.call_entity_method(
                            request, args[0], args[1], data)
            elif cargs == 3:
                # URL: /entity/collection/method
                reply = self.call_linked_collection_method(
                        request, args[0], args[1], args[2], data)
            elif cargs == 4:
                # URL: /entity/collection/entity/method
                reply = self.call_linked_entity_method(
                        request, args[0], args[1], args[2], args[3], data)
            else:
                raise TypeError()

            return self.reply_to_response(request, reply)

        except TypeError as e:
            if settings.DEBUG:
                raise Http404(str(e))
            else:
                raise Http404()

        except Exception as e:
            if settings.DEBUG:
                return HttpResponseBadRequest(str(e))
            else:
                return HttpResponseBadRequest()

    def put(self, request, *args):
        """Handle PUT request."""
        cargs = len(args)

        try:
            data = json.loads(request.body)
            if cargs == 1:
                # URL: /entity
                reply = self.edit_entity(request, args[0], data)
            else:
                raise TypeError()

            return self.reply_to_response(request, reply)

        except TypeError as e:
            if settings.DEBUG:
                raise Http404(str(e))
            else:
                raise Http404()

        except Exception as e:
            if settings.DEBUG:
                return HttpResponseBadRequest(str(e))
            else:
                return HttpResponseBadRequest()

    def delete(self, request, *args):
        """Handle DELETE request."""
        cargs = len(args)

        try:
            if cargs == 1:
                # URL: /entity
                reply = self.delete_entity(request, args[0])
            elif cargs == 3:
                # URL: /entity/collection/linked_entity
                reply = self.delete_linked_entity(request, args[0], args[1],
                        args[2])
            else:
                raise TypeError()

            return self.reply_to_response(request, reply)

        except TypeError as e:
            if settings.DEBUG:
                raise Http404(str(e))
            else:
                raise Http404()

        except Exception as e:
            if settings.DEBUG:
                return HttpResponseBadRequest(str(e))
            else:
                return HttpResponseBadRequest()

